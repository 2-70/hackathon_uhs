"""API 테스트가 매번 독립된 SQLite DB를 사용하도록 fixtures를 제공합니다."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import models  # noqa: F401 - Base metadata에 모델을 등록합니다.
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """테스트 하나가 끝나면 전체 스키마와 데이터를 버립니다."""

    # 메모리 SQLite를 한 커넥션으로 유지해 TestClient 스레드에서도 같은 DB를 봅니다.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 테스트 DB에 실제 모델 스키마를 생성합니다.
    Base.metadata.create_all(engine)
    # 테스트에서 사용할 세션 팩토리입니다.
    testing_session_local = sessionmaker(bind=engine, expire_on_commit=False)
    # 하나의 테스트 동안 라우터와 직접 DB 검증이 같은 세션을 사용하게 합니다.
    session = testing_session_local()
    try:
        yield session
    finally:
        # 테스트 종료 후 세션·테이블·엔진을 정리합니다.
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI의 DB 의존성을 테스트 세션으로 바꿉니다."""

    # 실제 파일 DB 대신 fixture 세션을 사용하도록 의존성을 오버라이드합니다.
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    # 테스트 시작 전에 앱의 DB 의존성을 교체합니다.
    app.dependency_overrides[get_db] = override_get_db
    try:
        # TestClient로 실제 HTTP 요청·응답 경로를 검증합니다.
        # 일반 개발 환경에서는 기본 asyncio 백엔드로 실제 HTTP 흐름을 검증합니다.
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # 다음 테스트가 실제 의존성을 사용할 수 있도록 원복합니다.
        app.dependency_overrides.clear()
