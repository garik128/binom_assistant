"""
Скрипт для применения миграции - удаление collector.interval_hours
"""
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import get_config

def apply_migration():
    """Применяет миграцию для удаления collector.interval_hours"""
    config = get_config()
    db_path = config.database_url.replace('sqlite:///', '')

    migration_file = Path(__file__).parent / "migration_remove_interval_hours.sql"
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем что есть до миграции
        cursor.execute("SELECT key, value FROM app_settings WHERE key = 'collector.interval_hours'")
        before = cursor.fetchone()

        if before:
            print(f"\nНастройка до миграции: {before[0]} = {before[1]}")
        else:
            print(f"\nНастройка collector.interval_hours не найдена в БД")

        # Применяем миграцию
        cursor.executescript(migration_sql)
        conn.commit()

        # Проверяем что удалилось
        cursor.execute("SELECT key FROM app_settings WHERE key = 'collector.interval_hours'")
        after = cursor.fetchone()

        if after is None:
            print(f"\nМиграция выполнена успешно!")
            print(f"Настройка collector.interval_hours удалена из БД")
            print(f"\nИнтервал сбора данных теперь управляется через schedule.daily_stats (cron)")
        else:
            print(f"\nОшибка: настройка не удалена")
            return False

        conn.close()
    except Exception as e:
        print(f"Ошибка при применении миграции: {e}")
        return False

    return True

if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
