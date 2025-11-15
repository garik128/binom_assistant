"""
Скрипт для применения миграции настройки API pause
"""
import sqlite3
import sys
from pathlib import Path

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import get_config

def apply_migration():
    """Применяет миграцию для добавления настройки collector.api_pause"""
    config = get_config()
    db_path = config.database_url.replace('sqlite:///', '')

    print(f"Применение миграции API pause...")
    print(f"База данных: {db_path}")

    # Читаем SQL миграцию
    migration_file = Path(__file__).parent / "migration_add_api_pause.sql"
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
        cursor.execute("SELECT key, value, value_type FROM app_settings WHERE key = 'collector.api_pause'")
        setting = cursor.fetchone()

        if setting:
            print(f"\nМиграция выполнена успешно!")
            print(f"Добавлена настройка: {setting[0]} = {setting[1]} (тип: {setting[2]})")
        else:
            print("\nНастройка уже существовала (INSERT OR IGNORE)")

        conn.close()

    except Exception as e:
        print(f"Ошибка при применении миграции: {e}")
        return False

    return True

if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
