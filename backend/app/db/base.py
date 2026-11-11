"""SQLAlchemy declarative base를 정의합니다."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 SQLAlchemy 모델이 상속하는 기본 클래스입니다."""
