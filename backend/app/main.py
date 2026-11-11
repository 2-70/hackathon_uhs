"""WashWise FastAPI 애플리케이션 진입점입니다."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.router import api_router, include_optional_ai_router
from backend.app.core.config import get_settings
from backend.app.core.errors import ApiError

# 내부 오류는 서버 로그에만 남기고 응답에는 안전한 공통 문구만 보냅니다.
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """앱 수명 주기에서 로그 설정을 적용합니다."""

    # 환경 설정과 같은 레벨의 로그 포맷을 사용해 오류 원인을 서버에서 추적합니다.
    logging.basicConfig(level=getattr(logging, get_settings().log_level.upper(), logging.INFO))
    # 현재는 시작 시 자동 마이그레이션을 하지 않아 배포 순서를 명확히 유지합니다.
    yield


# OpenAPI 문서에 실제 제품명을 표시합니다.
app = FastAPI(
    title=get_settings().app_name,
    version="0.1.0",
    description="옷장·공용 기기·사용자 기기 등록을 제공하는 WashWise 백엔드 기반",
    lifespan=lifespan,
)
# 모바일 개발 서버가 브라우저를 통해 API를 호출할 수 있도록 허용 주소를 등록합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 구현된 공용 API를 앱에 등록합니다.
app.include_router(api_router)
# AI 담당 라우터는 준비된 경우에만 규약에 따라 연결합니다.
include_optional_ai_router(app)


@app.exception_handler(ApiError)
async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    """도메인 오류를 계약된 error 객체로 변환합니다."""

    # 앱이 일관된 구조로 오류를 처리하도록 code·message·details를 감쌉니다.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic 입력 오류를 모바일 계약에 맞게 정리합니다."""

    # FastAPI의 위치·메시지 목록을 앱이 표시할 수 있는 단순한 details로 변환합니다.
    details = {
        "fields": [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
    }
    # 422는 필수값 누락과 자료형 오류를 구분하는 표준 상태 코드입니다.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": "요청 입력을 확인해 주세요.",
                "details": details,
            }
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_error(_: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI 기본 HTTP 오류도 같은 응답 형식으로 통일합니다."""

    # 프레임워크 기본 detail을 공개하되 내부 예외는 이 핸들러까지 오지 않습니다.
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": detail.get("code", "HTTP_ERROR"),
                "message": detail.get("message", str(exc.detail)),
                "details": None,
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """예상하지 못한 오류를 로그에 남기고 비밀정보 없는 응답을 보냅니다."""

    # 요청 경로와 traceback은 서버 운영자가 원인을 찾는 데 필요합니다.
    logger.exception("처리되지 않은 서버 오류: path=%s", request.url.path)
    # 클라이언트에는 DB URL·키·스택트레이스를 절대 반환하지 않습니다.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버에서 요청을 처리하지 못했습니다.",
                "details": None,
            }
        },
    )
