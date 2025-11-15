"""
Базовая настройка SQLAlchemy
"""
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from config.config import get_config


logger = logging.getLogger(__name__)

# Базовый класс для моделей
Base = declarative_base()

# Глобальные объекты
_engine = None
_session_factory = None


def get_engine():
    """
    Получает или создает движок SQLAlchemy
    """
    global _engine

    if _engine is None:
        config = get_config()
        database_url = config.database_url

        # Настройки для SQLite
        if database_url.startswith('sqlite'):
            connect_args = {
                "check_same_thread": False,
                "timeout": 30  # 30 секунд таймаут для locked database
            }
            echo = config.get('web.debug', False)
        else:
            connect_args = {}
            echo = config.get('web.debug', False)

        _engine = create_engine(
            database_url,
            echo=echo,
            connect_args=connect_args,
            pool_pre_ping=True  # Проверка соединения перед использованием
        )

        logger.info(f"Database engine created: {database_url.split('://')[0]}")

    return _engine


def get_session_factory():
    """
    Получает фабрику сессий
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = scoped_session(
            sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=engine
            )
        )

        logger.info("Session factory created")

    return _session_factory


def get_session():
    """
    Получает сессию для работы с БД (generator function)

    УСТАРЕЛО: Используйте session_scope() context manager вместо этого!

    Использование (НЕПРАВИЛЬНО - вызывает утечки):
        with next(get_session()) as session:  # НЕ ДЕЛАЙТЕ ТАК!
            # работа с БД

    Правильное использование:
        session_gen = get_session()
        session = next(session_gen)
        try:
            # работа с сессией
            session.commit()
        finally:
            try:
                next(session_gen, None)
            except StopIteration:
                pass
    """
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session error: {e}")
        raise
    finally:
        session.close()


@contextmanager
def session_scope():
    """
    Context manager для безопасной работы с сессией БД

    РЕКОМЕНДУЕТСЯ: Используйте этот метод вместо get_session()!

    Использование:
        from storage.database import session_scope

        with session_scope() as session:
            campaign = session.query(Campaign).filter_by(id=123).first()
            campaign.status = 'updated'
            # commit() вызывается автоматически при выходе из блока
            # rollback() вызывается автоматически при ошибке

    Returns:
        Session объект для работы с БД
    """
    factory = get_session_factory()
    session = factory()

    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Session error in session_scope: {e}")
        raise
    finally:
        session.close()


def create_tables():
    """
    Создает все таблицы в БД
    """
    # Импортируем модели после их определения
    # Это нужно вызывать ПОСЛЕ создания models.py
    try:
        from . import models  # noqa
    except ImportError:
        logger.warning("Models not yet created, Base.metadata will be empty")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("All tables created")


def drop_tables():
    """
    Удаляет все таблицы из БД (ОСТОРОЖНО!)
    """
    try:
        from . import models  # noqa
    except ImportError:
        logger.warning("Models not yet created")

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.warning("All tables dropped")
