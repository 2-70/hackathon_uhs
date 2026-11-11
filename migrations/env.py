"""Alembic이 앱 설정과 SQLAlchemy metadata를 사용하도록 연결합니다."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import get_settings
from backend.app.db import models  # noqa: F401 - metadata에 모든 모델을 등록합니다.
from backend.app.db.base import Base

# Alembic 설정 객체는 명령행에서 전달된 현재 migration context입니다.
config = context.config
# ini에 URL이 비어 있으면 앱이 읽은 DATABASE_URL을 사용합니다.
config.set_main_option("sqlalchemy.url", get_settings().migration_database_url.replace("%", "%%"))
# ini의 로깅 섹션이 있을 때만 기본 로깅을 적용합니다.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
# 모든 SQLAlchemy 모델의 metadata를 autogenerate와 migration에 제공합니다.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """DB 연결 없이 SQL 스크립트를 생성합니다."""

    # offline 모드에서는 URL과 metadata만으로 SQL을 출력합니다.
    url = config.get_main_option("sqlalchemy.url")
    # literal_binds를 켜 생성 SQL을 바로 검토할 수 있게 합니다.
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    # migration 단위의 트랜잭션 문맥을 시작합니다.
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """실제 DB에 연결해 migration을 실행합니다."""

    # Alembic 설정으로 SQLAlchemy 연결 엔진을 생성합니다.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # 연결을 열고 migration context를 구성합니다.
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        # 한 migration 명령이 하나의 트랜잭션으로 처리되게 합니다.
        with context.begin_transaction():
            context.run_migrations()


# Alembic이 offline/online 실행 방식을 선택합니다.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
