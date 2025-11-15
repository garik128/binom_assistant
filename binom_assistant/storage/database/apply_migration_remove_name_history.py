#!/usr/bin/env python3
"""
Применение миграции: Удаление поля name_history из campaigns
Дата: 2025-10-25
"""

import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime

# Путь к БД
DB_PATH = Path(__file__).parent.parent.parent.parent / "binom_assistant" / "data" / "binom_assistant.db"
MIGRATION_FILE = Path(__file__).parent / "migration_remove_name_history.sql"


def backup_database():
    """Создает резервную копию БД"""
    if not DB_PATH.exists():
        print(f"БД не найдена: {DB_PATH}")
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"binom_assistant_{timestamp}_before_remove_name_history.db"

    print(f"Создаем резервную копию: {backup_path}")
    shutil.copy2(DB_PATH, backup_path)
    print("Резервная копия создана!")
    return True


def check_name_history_data():
    """Проверяет есть ли данные в name_history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM campaigns
        WHERE name_history IS NOT NULL AND name_history != '[]'
    """)
    count = cursor.fetchone()[0]
    conn.close()

    return count


def apply_migration():
    """Применяет миграцию"""
    if not MIGRATION_FILE.exists():
        print(f"Файл миграции не найден: {MIGRATION_FILE}")
        return False

    # Читаем SQL миграции
    with open(MIGRATION_FILE, 'r', encoding='utf-8') as f:
        migration_sql = f.read()

    # Применяем
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("\nПрименяем миграцию...")
        cursor.executescript(migration_sql)
        conn.commit()
        print("Миграция успешно применена!")
        return True
    except Exception as e:
        print(f"Ошибка при применении миграции: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify_migration():
    """Проверяет что миграция применена"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверяем структуру таблицы
    cursor.execute("PRAGMA table_info(campaigns)")
    columns = [row[1] for row in cursor.fetchall()]

    # Проверяем что name_history нет
    has_name_history = 'name_history' in columns

    # Проверяем что данные на месте
    cursor.execute("SELECT COUNT(*) FROM campaigns")
    count = cursor.fetchone()[0]

    conn.close()

    if has_name_history:
        print("\nОШИБКА: Колонка name_history все еще существует!")
        return False

    print(f"\nПроверка успешна:")
    print(f"  - Колонка name_history удалена")
    print(f"  - Количество кампаний: {count}")
    print(f"  - Колонки в таблице: {', '.join(columns)}")
    return True


def main():
    print("=" * 60)
    print("Миграция: Удаление поля name_history из campaigns")
    print("=" * 60)

    # Проверяем существование БД
    if not DB_PATH.exists():
        print(f"\nБД не найдена: {DB_PATH}")
        print("Миграция не требуется - БД будет создана с новой схемой.")
        return

    # Проверяем есть ли данные в name_history
    count = check_name_history_data()
    if count > 0:
        print(f"\nВНИМАНИЕ: Найдено {count} кампаний с данными в name_history")
        print("Эти данные будут потеряны, но они должны быть в таблице name_changes")
        response = input("Продолжить? (yes/no): ")
        if response.lower() != 'yes':
            print("Миграция отменена.")
            return
    else:
        print("\nДанных в name_history нет - можно безопасно удалить колонку.")

    # Создаем бэкап
    if not backup_database():
        return

    # Применяем миграцию
    if not apply_migration():
        print("\nМиграция не удалась. Восстановите из резервной копии если нужно.")
        return

    # Проверяем результат
    if verify_migration():
        print("\n" + "=" * 60)
        print("МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 60)
    else:
        print("\nПроверка не прошла. Восстановите из резервной копии.")


if __name__ == "__main__":
    main()
