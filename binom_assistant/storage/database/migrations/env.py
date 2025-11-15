"""
Окружение Alembic для миграций
"""
import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Импортируем наши модели
from storage.database.base import Base
from storage.database import models  # noqa - нужно чтобы все модели зарегистрировались
from config import get_config

# Это объект конфигурации Alembic
config = context.config

# Настройка логирования из конфигурации
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные для автогенерации
target_metadata = Base.metadata


def get_url():
    """
    Получает URL базы данных из нашего конфига
    """
    app_config = get_config()
    return app_config.database_url


def run_migrations_offline() -> None:
    """
    Запуск миграций в 'offline' режиме.

    Генерирует SQL скрипт без подключения к БД.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Запуск миграций в 'online' режиме.

    Подключается к БД и применяет миграции.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
