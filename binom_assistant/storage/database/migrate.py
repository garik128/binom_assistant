"""
Утилита для управления миграциями
"""
import os
import sys
from pathlib import Path
from alembic.config import Config
from alembic import command


def get_alembic_config():
    """
    Получает конфигурацию Alembic
    """
    # Путь к корню проекта
    project_root = Path(__file__).parent.parent.parent

    # Путь к alembic.ini
    alembic_ini = project_root / "storage" / "database" / "alembic.ini"

    if not alembic_ini.exists():
        raise FileNotFoundError(f"Не найден файл {alembic_ini}")

    # Создаем конфиг
    config = Config(str(alembic_ini))

    # Устанавливаем путь к миграциям
    migrations_path = project_root / "storage" / "database" / "migrations"
    config.set_main_option("script_location", str(migrations_path))

    return config


def upgrade(revision='head'):
    """
    Применить миграции

    Args:
        revision: до какой версии мигрировать (по умолчанию 'head' - последняя)
    """
    config = get_alembic_config()
    command.upgrade(config, revision)
    print(f"[OK] Migrations applied to version: {revision}")


def downgrade(revision='-1'):
    """
    Откатить миграции

    Args:
        revision: до какой версии откатить (по умолчанию -1 - на одну назад)
    """
    config = get_alembic_config()
    command.downgrade(config, revision)
    print(f"✓ Миграции откачены до версии: {revision}")


def current():
    """
    Показать текущую версию БД
    """
    config = get_alembic_config()
    command.current(config)


def history():
    """
    Показать историю миграций
    """
    config = get_alembic_config()
    command.history(config)


def revision(message, autogenerate=False):
    """
    Создать новую миграцию

    Args:
        message: описание миграции
        autogenerate: автоматически определить изменения в моделях
    """
    config = get_alembic_config()
    command.revision(config, message=message, autogenerate=autogenerate)
    print(f"✓ Миграция создана: {message}")


if __name__ == "__main__":
    """
    Запуск из командной строки

    Примеры:
        python migrate.py upgrade
        python migrate.py downgrade
        python migrate.py current
        python migrate.py history
    """
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python migrate.py upgrade [revision]")
        print("  python migrate.py downgrade [revision]")
        print("  python migrate.py current")
        print("  python migrate.py history")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "upgrade":
        rev = sys.argv[2] if len(sys.argv) > 2 else 'head'
        upgrade(rev)
    elif cmd == "downgrade":
        rev = sys.argv[2] if len(sys.argv) > 2 else '-1'
        downgrade(rev)
    elif cmd == "current":
        current()
    elif cmd == "history":
        history()
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)
