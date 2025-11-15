"""
Скрипт применения миграции: Добавление индексов для поиска по названиям и датам

TODO 10: Добавить индексы для поиска по названиям и датам

Дата: 2025-10-25
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import shutil

# Определяем пути
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR.parent.parent / "data" / "binom_assistant.db"
MIGRATION_SQL = SCRIPT_DIR / "migration_add_search_indexes.sql"


def create_backup(db_path: Path) -> Path:
    """Создает резервную копию базы данных"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def check_indexes_exist(conn: sqlite3.Connection) -> dict:
    """Проверяет наличие индексов"""
    cursor = conn.cursor()

    indexes_to_check = [
        'idx_campaigns_name',
        'idx_campaigns_last_seen',
        'idx_campaigns_created_at',
        'idx_campaigns_active_group'
    ]

    result = {}
    for index_name in indexes_to_check:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,)
        )
        result[index_name] = cursor.fetchone() is not None

    return result


def get_table_stats(conn: sqlite3.Connection) -> dict:
    """Получает статистику по таблице campaigns"""
    cursor = conn.cursor()

    # Общее количество кампаний
    cursor.execute("SELECT COUNT(*) FROM campaigns")
    total = cursor.fetchone()[0]

    # Активные кампании
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE is_active = TRUE")
    active = cursor.fetchone()[0]

    # Уникальные группы
    cursor.execute("SELECT COUNT(DISTINCT group_name) FROM campaigns")
    groups = cursor.fetchone()[0]

    return {
        'total_campaigns': total,
        'active_campaigns': active,
        'unique_groups': groups
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
            indexes_before = check_indexes_exist(conn)
            for idx_name, exists in indexes_before.items():
                status = "существует" if exists else "отсутствует"
                print(f"  - {idx_name}: {status}")

            stats = get_table_stats(conn)
            print(f"\nСтатистика таблицы campaigns:")
            print(f"  - Всего кампаний: {stats['total_campaigns']}")
            print(f"  - Активных: {stats['active_campaigns']}")
            print(f"  - Уникальных групп: {stats['unique_groups']}")

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
            indexes_after = check_indexes_exist(conn)
            created_count = 0
            for idx_name, exists in indexes_after.items():
                if exists and not indexes_before.get(idx_name, False):
                    print(f"  - {idx_name}: создан")
                    created_count += 1
                elif exists:
                    print(f"  - {idx_name}: уже существовал")
                else:
                    print(f"  - {idx_name}: ОШИБКА - не создан!")

            print(f"\nСоздано новых индексов: {created_count}")

            # Анализ индексов (для оптимизации)
            print("\nОбновление статистики индексов...")
            cursor.execute("ANALYZE campaigns")
            conn.commit()
            print("Статистика обновлена")

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
    print("Миграция: Добавление индексов для поиска по названиям и датам")
    print("TODO 10")
    print("=" * 70)

    success = apply_migration(DB_PATH, MIGRATION_SQL)

    print("\n" + "=" * 70)
    if success:
        print("МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
        print("\nНовые индексы ускорят следующие запросы:")
        print("  1. Поиск кампаний по названию (LIKE '%keyword%')")
        print("  2. Фильтрация по последнему обновлению (last_seen)")
        print("  3. Сортировка по дате создания (created_at)")
        print("  4. Активные кампании по группе (is_active + group_name)")
        return 0
    else:
        print("МИГРАЦИЯ ЗАВЕРШИЛАСЬ С ОШИБКАМИ")
        print(f"\nДля отката используйте резервную копию из папки: {DB_PATH.parent}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
