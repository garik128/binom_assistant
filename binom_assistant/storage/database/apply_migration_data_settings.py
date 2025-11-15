"""
Скрипт для применения миграции настроек хранения данных
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import get_config

def apply_migration():
    """Применяет миграцию для добавления настроек хранения данных"""
    config = get_config()
    db_path = config.database_url.replace('sqlite:///', '')

    print(f"Применение миграции настроек хранения данных...")
    print(f"База данных: {db_path}")

    # Читаем SQL миграцию
    migration_file = Path(__file__).parent / "migration_add_data_settings.sql"
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()

    try:
        # Подключаемся к БД
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Выполняем миграцию
        cursor.executescript(migration_sql)
        conn.commit()

        # Проверяем результат
        cursor.execute("SELECT key, value, category FROM app_settings WHERE category = 'data' OR key = 'schedule.cleanup'")
        settings = cursor.fetchall()

        print("\nМиграция выполнена успешно!")
        print(f"\nДобавлено/обновлено настроек: {len(settings)}")
        print("\nСписок настроек:")
        for key, value, category in settings:
            print(f"  - {key} = {value} (категория: {category})")

        conn.close()

    except Exception as e:
        print(f"Ошибка при применении миграции: {e}")
        return False

    return True

if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
