"""공용 라우터와 AI 담당 라우터의 연결 지점을 관리합니다."""

import importlib
import logging
from types import ModuleType

from fastapi import APIRouter, FastAPI

from backend.app.api.routes import health, machines, user_machines, wardrobe
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

# 각 도메인 라우터를 한 앱에 합쳐 OpenAPI와 테스트 진입점을 단순하게 합니다.
api_router = APIRouter()
# 서버 상태 API를 등록합니다.
api_router.include_router(health.router)
# 옷장 CRUD API를 등록합니다.
api_router.include_router(wardrobe.router)
# 공용 모델·코스 조회 API를 등록합니다.
api_router.include_router(machines.router)
# 사용자 기기 등록·복원 API를 등록합니다.
api_router.include_router(user_machines.router)


def _load_ai_router_module() -> ModuleType | None:
    """AI 담당자가 제공하는 선택적 router 모듈을 가져옵니다."""

    try:
        # AI 담당 소유 경로의 계약된 모듈 이름만 조회하고 파일을 대신 만들지 않습니다.
        return importlib.import_module("backend.app.ai.router")
    except ModuleNotFoundError as exc:
        # 아직 AI 라우터가 없을 때 공용 서버가 시작되는 것이 정상입니다.
        if exc.name == "backend.app.ai" or exc.name == "backend.app.ai.router":
            return None
        # AI 모듈 내부 의존성 누락은 조용히 숨기지 않고 설정 오류로 알립니다.
        raise


def include_optional_ai_router(app: FastAPI) -> None:
    """설정이 켜져 있고 AI router가 존재하면 `/api` 아래에 연결합니다."""

    # 기본값 false로 두어 AI 담당자의 작업이 끝나기 전에도 서버가 동작하게 합니다.
    settings = get_settings()
    if not settings.enable_ai_router:
        return
    # 모듈을 동적으로 읽어 담당 파일을 임의로 수정하지 않습니다.
    ai_module = _load_ai_router_module()
    if ai_module is None:
        # 연결을 요청했지만 아직 파일이 없다는 사실을 로그로 남깁니다.
        logger.warning("AI router가 없어 선택적 연결을 건너뜁니다.")
        return
    # AI 담당자는 모듈 수준의 `router` 객체를 제공해야 합니다.
    ai_router = getattr(ai_module, "router", None)
    if ai_router is None:
        # 규약을 지키지 않은 모듈은 서버 시작 전에 명확히 알립니다.
        raise RuntimeError("backend.app.ai.router.router가 필요합니다.")
    # AI 경로도 공용 API의 `/api` 접두사를 사용하도록 연결합니다.
    app.include_router(ai_router, prefix="/api")
