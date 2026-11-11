"""Alembic 추가형 migration이 기존 행과 ID를 보존하는지 검증합니다."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from backend.app.core.config import get_settings


def test_existing_rows_survive_analysis_and_planning_migrations(tmp_path, monkeypatch):
    """0001 데이터가 0002·0003 적용 뒤에도 같은 ID와 값으로 남아야 합니다."""

    database_path = Path(tmp_path) / "existing-data.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    # Alembic env.py가 테스트 전용 DB만 보도록 환경 변수를 덮어씁니다.
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", database_url)
    get_settings.cache_clear()

    config = Config("alembic.ini")
    # 먼저 기존 서비스와 같은 0001 구조까지만 만듭니다.
    command.upgrade(config, "0001_initial_schema")
    engine = create_engine(database_url)
    # raw SQLite INSERT에서는 ISO 문자열을 사용해 Python 기본 datetime 어댑터에 의존하지 않습니다.
    now = "2026-11-11T00:00:00+00:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO wardrobe_items (
                    id, owner_id, item_name, source_type, verification_status,
                    created_at, updated_at
                ) VALUES (
                    :id, :owner_id, :item_name, :source_type, :verification_status,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": "existing-wardrobe-id",
                "owner_id": "demo-user",
                "item_name": "기존 셔츠",
                "source_type": "user_input",
                "verification_status": "unconfirmed",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO user_machines (
                    id, owner_id, machine_type, display_name, notes,
                    created_at, updated_at
                ) VALUES (
                    :id, :owner_id, :machine_type, :display_name, :notes,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": "existing-machine-id",
                "owner_id": "demo-user",
                "machine_type": "washer",
                "display_name": "기존 세탁기",
                "notes": "보존 확인",
                "created_at": now,
                "updated_at": now,
            },
        )

    # 삭제·이름 변경 없이 새 칼럼과 테이블만 추가합니다.
    command.upgrade(config, "head")
    with engine.connect() as connection:
        wardrobe = connection.execute(
            text(
                "SELECT id, item_name, care_wash_strength "
                "FROM wardrobe_items WHERE id = :id"
            ),
            {"id": "existing-wardrobe-id"},
        ).one()
        machine = connection.execute(
            text("SELECT id, display_name, notes FROM user_machines WHERE id = :id"),
            {"id": "existing-machine-id"},
        ).one()

    assert tuple(wardrobe) == ("existing-wardrobe-id", "기존 셔츠", None)
    assert tuple(machine) == ("existing-machine-id", "기존 세탁기", "보존 확인")
    engine.dispose()
    get_settings.cache_clear()
