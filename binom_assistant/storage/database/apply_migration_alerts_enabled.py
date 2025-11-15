"""
Применяет миграцию для добавления поля alerts_enabled
"""
import sqlite3
import os
import sys
from pathlib import Path

# Добавляем путь к корню проекта
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from config.config import get_config


def apply_migration():
    """Применяет миграцию добавления alerts_enabled"""
    config = get_config()
    db_url = config.database_url
    # Извлекаем путь из database_url (sqlite:///path/to/db.sqlite)
    if db_url.startswith('sqlite:///'):
        db_path = db_url.replace('sqlite:///', '')
    else:
        print(f"Неподдерживаемый тип БД: {db_url}")
        return False
    migration_sql_path = Path(__file__).parent / "migration_add_alerts_enabled.sql"

    if not os.path.exists(db_path):
        print(f"База данных не найдена: {db_path}")
        return False

    if not os.path.exists(migration_sql_path):
        print(f"Файл миграции не найден: {migration_sql_path}")
        return False

    print(f"Применение миграции к базе данных: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем, есть ли уже колонка alerts_enabled
        cursor.execute("PRAGMA table_info(module_configs)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'alerts_enabled' in columns:
            print("Колонка alerts_enabled уже существует. Миграция уже применена.")
            conn.close()
            return True

        # Читаем SQL миграцию
        with open(migration_sql_path, 'r', encoding='utf-8') as f:
            migration_sql = f.read()

        # Выполняем миграцию
        cursor.executescript(migration_sql)
        conn.commit()

        # Проверяем что колонка добавлена
        cursor.execute("PRAGMA table_info(module_configs)")
        columns_after = [col[1] for col in cursor.fetchall()]

        if 'alerts_enabled' in columns_after:
            print("Миграция успешно применена!")

            # Показываем статус для критических модулей
            cursor.execute("""
                SELECT module_id, alerts_enabled
                FROM module_configs
                WHERE module_id IN (
                    'bleeding_detector',
                    'zero_approval_alert',
                    'spend_spike_monitor',
                    'waste_campaign_finder',
                    'traffic_quality_crash',
                    'squeezed_offer'
                )
            """)
            critical_modules = cursor.fetchall()

            if critical_modules:
                print("\nКритические модули с включенными алертами:")
                for module_id, alerts_enabled in critical_modules:
                    status = "Включено" if alerts_enabled else "Выключено"
                    print(f"  - {module_id}: {status}")

            conn.close()
            return True
        else:
            print("ОШИБКА: Колонка не была добавлена")
            conn.close()
            return False

    except sqlite3.Error as e:
        print(f"Ошибка SQLite: {e}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
