"""
Скрипт для применения миграции - удаление неиспользуемых настроек
"""
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import get_config

def apply_migration():
    """Применяет миграцию для удаления неиспользуемых настроек"""
    config = get_config()
    db_path = config.database_url.replace('sqlite:///', '')

    migration_file = Path(__file__).parent / "migration_remove_unused_settings.sql"
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем что есть до миграции
        cursor.execute("SELECT key FROM app_settings WHERE key IN ('schedule.cleanup', 'data.cleanup_aggressive')")
        before = cursor.fetchall()
        print(f"\nНастройки до миграции: {[row[0] for row in before]}")

        # Применяем миграцию
        cursor.executescript(migration_sql)
        conn.commit()

        # Проверяем что удалилось
        cursor.execute("SELECT key FROM app_settings WHERE key IN ('schedule.cleanup', 'data.cleanup_aggressive')")
        after = cursor.fetchall()

        if len(after) == 0:
            print(f"\nМиграция выполнена успешно!")
            print(f"Удалено настроек: {len(before)}")
            for row in before:
                print(f"  - {row[0]}")
        else:
            print(f"\nОшибка: не все настройки удалены")
            print(f"Осталось: {[row[0] for row in after]}")
            return False

        conn.close()
    except Exception as e:
        print(f"Ошибка при применении миграции: {e}")
        return False

    return True

if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
