"""
Скрипт применения миграции: Добавление таблицы app_settings для хранения настроек приложения

Система настроек с приоритетом БД -> .env -> defaults

Дата: 2025-11-01
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import shutil

# Определяем пути
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR.parent.parent / "data" / "binom_assistant.db"
MIGRATION_SQL = SCRIPT_DIR / "migration_add_app_settings.sql"


def create_backup(db_path: Path) -> Path:
    """Создает резервную копию базы данных"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def check_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Проверяет наличие таблицы"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def get_settings_stats(conn: sqlite3.Connection) -> dict:
    """Получает статистику по таблице app_settings"""
    cursor = conn.cursor()

    if not check_table_exists(conn, 'app_settings'):
        return {'exists': False}

    # Общее количество настроек
    cursor.execute("SELECT COUNT(*) FROM app_settings")
    total = cursor.fetchone()[0]

    # Количество по категориям
    cursor.execute("""
        SELECT category, COUNT(*)
        FROM app_settings
        GROUP BY category
    """)
    by_category = dict(cursor.fetchall())

    # Редактируемые настройки
    cursor.execute("SELECT COUNT(*) FROM app_settings WHERE is_editable = 1")
    editable = cursor.fetchone()[0]

    return {
        'exists': True,
        'total': total,
        'by_category': by_category,
        'editable': editable
    }


def apply_migration(db_path: Path, migration_sql: Path) -> bool:
    """Применяет миграцию к базе данных"""
    try:
        # Проверяем существование файлов
        if not db_path.exists():
            print(f"ОШИБКА: База данных не найдена: {db_path}")
            return False

        if not migration_sql.exists():
            print(f"ОШИБКА: Файл миграции не найден: {migration_sql}")
            return False

        # Создаем резервную копию
        print("Создание резервной копии базы данных...")
        backup_path = create_backup(db_path)
        print(f"Резервная копия создана: {backup_path}")

        # Подключаемся к БД
        print(f"\nПодключение к базе данных: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            # Проверяем текущее состояние
            print("\nТекущее состояние:")
            table_exists_before = check_table_exists(conn, 'app_settings')
            if table_exists_before:
                print("  - Таблица app_settings: уже существует")
                stats_before = get_settings_stats(conn)
                if stats_before['exists']:
                    print(f"  - Настроек в БД: {stats_before['total']}")
            else:
                print("  - Таблица app_settings: отсутствует")

            # Читаем SQL миграции
            with open(migration_sql, 'r', encoding='utf-8') as f:
                migration_commands = f.read()

            # Применяем миграцию
            print(f"\nПрименение миграции из: {migration_sql}")
            cursor = conn.cursor()
            cursor.executescript(migration_commands)
            conn.commit()
            print("Миграция успешно применена!")

            # Проверяем результат
            print("\nСостояние после миграции:")
            table_exists_after = check_table_exists(conn, 'app_settings')

            if table_exists_after:
                print("  - Таблица app_settings: создана")
                stats_after = get_settings_stats(conn)

                if stats_after['exists']:
                    print(f"  - Всего настроек: {stats_after['total']}")
                    print(f"  - Редактируемых: {stats_after['editable']}")
                    print(f"\n  Настроек по категориям:")
                    for category, count in stats_after['by_category'].items():
                        print(f"    - {category}: {count}")

                # Показываем созданные настройки
                cursor.execute("SELECT key, value, category, description FROM app_settings ORDER BY category, key")
                settings = cursor.fetchall()

                print(f"\n  Созданные настройки ({len(settings)}):")
                current_category = None
                for key, value, category, description in settings:
                    if category != current_category:
                        print(f"\n    [{category}]")
                        current_category = category
                    print(f"      {key} = {value}")
                    if description:
                        print(f"        ({description})")
            else:
                print("  - ОШИБКА: Таблица не создана!")

            return True

        finally:
            conn.close()

    except Exception as e:
        print(f"\nОШИБКА при применении миграции: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Главная функция"""
    print("=" * 70)
    print("Миграция: Добавление таблицы app_settings")
    print("Система настроек с приоритетом БД -> .env -> defaults")
    print("=" * 70)

    success = apply_migration(DB_PATH, MIGRATION_SQL)

    print("\n" + "=" * 70)
    if success:
        print("МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
        print("\nТаблица app_settings создана и заполнена дефолтными значениями:")
        print("  1. collector.update_days = 7 (диапазон: 1-365)")
        print("  2. collector.interval_hours = 1 (диапазон: 1-24)")
        print("  3. schedule.daily_stats = '0 * * * *'")
        print("  4. schedule.weekly_stats = '0 4 * * 1'")
        print("\nПриоритет значений: БД -> .env -> hardcoded defaults")
        return 0
    else:
        print("МИГРАЦИЯ ЗАВЕРШИЛАСЬ С ОШИБКАМИ")
        print(f"\nДля отката используйте резервную копию из папки: {DB_PATH.parent}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
