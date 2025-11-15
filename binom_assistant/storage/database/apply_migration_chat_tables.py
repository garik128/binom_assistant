#!/usr/bin/env python3
"""
Миграция: Добавление таблиц для чата (chat_sessions, chat_messages)

Создает:
- chat_sessions: хранение сессий чата
- chat_messages: хранение сообщений в рамках сессий
"""
import sys
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from storage.database.base import get_engine, get_session_factory
from storage.database.models import ChatSession, ChatMessage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_table_exists(table_name: str) -> bool:
    """
    Проверяет существование таблицы в БД.

    Args:
        table_name: Имя таблицы

    Returns:
        True если таблица существует
    """
    engine = get_engine()
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def apply_migration():
    """
    Применяет миграцию для создания таблиц чата.
    """
    logger.info("=" * 60)
    logger.info("Начало миграции: Добавление таблиц чата")
    logger.info("=" * 60)

    engine = get_engine()
    session_factory = get_session_factory()
    session = session_factory()

    try:
        # Проверяем существование таблиц
        sessions_exists = check_table_exists('chat_sessions')
        messages_exists = check_table_exists('chat_messages')

        if sessions_exists and messages_exists:
            logger.info("Таблицы chat_sessions и chat_messages уже существуют")
            logger.info("Миграция не требуется")
            return

        # Создаем таблицы если их нет
        if not sessions_exists:
            logger.info("Создание таблицы chat_sessions...")
            ChatSession.__table__.create(engine, checkfirst=True)
            logger.info("[OK] Таблица chat_sessions создана")

        if not messages_exists:
            logger.info("Создание таблицы chat_messages...")
            ChatMessage.__table__.create(engine, checkfirst=True)
            logger.info("[OK] Таблица chat_messages создана")

        # Проверяем результат
        inspector = inspect(engine)

        # Информация о chat_sessions
        if 'chat_sessions' in inspector.get_table_names():
            columns = inspector.get_columns('chat_sessions')
            logger.info(f"Таблица chat_sessions имеет {len(columns)} колонок:")
            for col in columns:
                logger.info(f"  - {col['name']}: {col['type']}")

        # Информация о chat_messages
        if 'chat_messages' in inspector.get_table_names():
            columns = inspector.get_columns('chat_messages')
            logger.info(f"Таблица chat_messages имеет {len(columns)} колонок:")
            for col in columns:
                logger.info(f"  - {col['name']}: {col['type']}")

        session.commit()
        logger.info("=" * 60)
        logger.info("Миграция успешно завершена!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    apply_migration()
