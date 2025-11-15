"""
Миграция БД: Добавление индексов для фильтрации шума

Добавляет композитный индекс для оптимизации запросов,
которые фильтруют кампании по cost >= 1$ и clicks >= 50.

Использование:
    python binom_assistant/storage/database/apply_migration_noise_filter_index.py
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from shutil import copy2

# Добавляем корневую папку проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def backup_database(db_path: str) -> str:
    """
    Создает резервную копию базы данных

    Args:
        db_path: путь к БД

    Returns:
        Путь к файлу резервной копии
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"

    print(f"Создание резервной копии БД...")
    print(f"  Исходный файл: {db_path}")
    print(f"  Резервная копия: {backup_path}")

    copy2(db_path, backup_path)
    print("Резервная копия создана успешно")

    return backup_path


def check_index_exists(cursor: sqlite3.Cursor, index_name: str) -> bool:
    """
    Проверяет существование индекса

    Args:
        cursor: курсор БД
        index_name: имя индекса

    Returns:
        True если индекс существует
    """
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def apply_migration(db_path: str):
    """
    Применяет миграцию к базе данных

    Args:
        db_path: путь к БД
    """
    print("\n" + "="*60)
    print("Миграция: Добавление индексов для фильтрации шума")
    print("="*60 + "\n")

    # Проверяем существование БД
    if not os.path.exists(db_path):
        print(f"ОШИБКА: База данных не найдена: {db_path}")
        return False

    # Создаем резервную копию
    backup_path = backup_database(db_path)

    try:
        # Подключаемся к БД
        print("\nПодключение к БД...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Проверяем текущие индексы
        print("\nТекущие индексы таблицы stats_daily:")
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='stats_daily'"
        )
        for row in cursor.fetchall():
            print(f"  - {row[0]}")

        # Индекс 1: Композитный индекс для фильтрации
        index1_name = "idx_stats_daily_cost_clicks"
        print(f"\nПроверка индекса {index1_name}...")

        if check_index_exists(cursor, index1_name):
            print(f"  Индекс {index1_name} уже существует, пропускаем")
        else:
            print(f"  Создание индекса {index1_name}...")
            cursor.execute("""
                CREATE INDEX idx_stats_daily_cost_clicks
                ON stats_daily(cost, clicks, campaign_id, date)
            """)
            print(f"  Индекс {index1_name} создан успешно")

        # Индекс 2: Частичный индекс для активных кампаний
        index2_name = "idx_stats_daily_active_campaigns"
        print(f"\nПроверка индекса {index2_name}...")

        if check_index_exists(cursor, index2_name):
            print(f"  Индекс {index2_name} уже существует, пропускаем")
        else:
            print(f"  Создание частичного индекса {index2_name}...")
            cursor.execute("""
                CREATE INDEX idx_stats_daily_active_campaigns
                ON stats_daily(campaign_id, date, cost, clicks)
                WHERE cost >= 1.0 AND clicks >= 50
            """)
            print(f"  Индекс {index2_name} создан успешно")

        # Сохраняем изменения
        conn.commit()

        # Проверяем результат
        print("\nНовые индексы таблицы stats_daily:")
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='stats_daily'"
        )
        for row in cursor.fetchall():
            print(f"  - {row[0]}")

        # Статистика по индексам
        print("\nСтатистика по индексам:")
        cursor.execute("SELECT COUNT(*) FROM stats_daily")
        total_rows = cursor.fetchone()[0]
        print(f"  Всего записей в stats_daily: {total_rows}")

        cursor.execute(
            "SELECT COUNT(*) FROM stats_daily WHERE cost >= 1.0 AND clicks >= 50"
        )
        filtered_rows = cursor.fetchone()[0]
        print(f"  Записей с cost >= 1$ и clicks >= 50: {filtered_rows}")
        print(f"  Процент от общего: {filtered_rows/total_rows*100:.1f}%")

        # Закрываем соединение
        conn.close()

        print("\n" + "="*60)
        print("МИГРАЦИЯ ВЫПОЛНЕНА УСПЕШНО")
        print("="*60)
        print(f"\nРезервная копия сохранена: {backup_path}")
        print("Если возникли проблемы, восстановите БД из резервной копии.\n")

        return True

    except Exception as e:
        print(f"\n ОШИБКА при выполнении миграции: {e}")
        print(f"Восстановление из резервной копии: {backup_path}")

        # Восстанавливаем из резервной копии
        if os.path.exists(backup_path):
            copy2(backup_path, db_path)
            print("БД успешно восстановлена из резервной копии")

        return False


def main():
    """
    Основная функция
    """
    # Путь к БД
    db_path = project_root / "binom_assistant" / "data" / "binom_assistant.db"

    print(f"Путь к проекту: {project_root}")
    print(f"Путь к БД: {db_path}")

    # Применяем миграцию
    success = apply_migration(str(db_path))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
