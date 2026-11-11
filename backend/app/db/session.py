"""SQLAlchemy 엔진과 요청 단위 세션을 설정합니다."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings

# 모든 모듈이 같은 설정으로 같은 연결 풀을 사용하도록 엔진을 한 번만 만듭니다.
settings = get_settings()
# SQLite는 다중 스레드 테스트 클라이언트에서 연결을 공유해야 하므로 별도 옵션을 사용합니다.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# 운영 PostgreSQL에서는 끊긴 연결을 재사용하지 않도록 pre-ping을 켭니다.
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
# 요청마다 독립 세션을 만들고 자동 커밋은 라우터가 명시적으로 수행하게 합니다.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """요청에 DB 세션을 제공하고 오류 시 롤백한 뒤 닫습니다."""

    # 세션 객체를 요청 범위에 한 개만 생성합니다.
    db = SessionLocal()
    try:
        # FastAPI가 라우터 함수에 세션을 주입합니다.
        yield db
    except Exception:
        # 라우터가 예외를 던져도 미완료 트랜잭션이 다음 요청으로 넘어가지 않게 합니다.
        db.rollback()
        raise
    finally:
        # 연결을 풀로 반환해 요청이 쌓여도 연결이 고갈되지 않게 합니다.
        db.close()
