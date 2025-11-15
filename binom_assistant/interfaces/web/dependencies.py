"""
Зависимости для FastAPI endpoints.
"""
from typing import Generator
from sqlalchemy.orm import Session
from storage.database import get_session
import logging

logger = logging.getLogger(__name__)


def get_db() -> Generator[Session, None, None]:
    """
    Зависимость для получения сессии БД.

    Yields:
        Session: Сессия SQLAlchemy
    """
    # Используем генератор get_session из storage.database
    session_generator = get_session()
    db = next(session_generator)
    try:
        yield db
    finally:
        try:
            next(session_generator)
        except StopIteration:
            pass
