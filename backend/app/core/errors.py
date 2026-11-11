"""앱 전체에서 같은 오류 응답을 만들기 위한 예외 정의입니다."""

from typing import Any


class ApiError(Exception):
    """클라이언트에 안전하게 공개할 수 있는 도메인 오류입니다."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: Any | None = None,
    ) -> None:
        # 앱이 상태 코드 대신 분기할 수 있도록 안정적인 오류 코드를 보관합니다.
        self.code = code
        # 사용자에게 표시할 수 있는 설명만 저장하고 내부 예외 문자열은 넣지 않습니다.
        self.message = message
        # HTTP 상태 코드는 라우터가 아니라 공통 핸들러가 응답에 반영합니다.
        self.status_code = status_code
        # 필드 오류나 참조 ID처럼 선택적으로 필요한 정보만 담습니다.
        self.details = details
        # 기본 Exception 메시지도 설정해 서버 로그에서 오류를 식별할 수 있게 합니다.
        super().__init__(message)
