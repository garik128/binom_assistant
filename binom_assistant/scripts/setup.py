"""
Скрипт первоначальной настройки проекта
"""
import os
import sys
from pathlib import Path
import shutil


def create_env_file():
    """
    Создает .env файл из примера
    """
    root = Path(__file__).parent.parent
    example_env = root / ".env.example"
    env_file = root / ".env"

    if env_file.exists():
        print("Файл .env уже существует")
        # Валидируем существующий файл
        if not validate_env_file():
            print("\nWARNING: Пожалуйста, отредактируй .env и замени все placeholder значения реальными данными!")
        return

    shutil.copy(example_env, env_file)
    print("Создан файл .env из .env.example")
    print("\nВАЖНО: Отредактируй файл .env и замени все placeholder значения:")
    print("  - BINOM_URL")
    print("  - BINOM_API_KEY")
    print("  - TELEGRAM_BOT_TOKEN")
    print("  - TELEGRAM_CHAT_ID")
    print("  - AI_API_KEY")


def validate_env_file():
    """
    Валидирует что .env был кастомизирован.

    Returns:
        bool: True если .env валиден, False если содержит placeholders
    """
    root = Path(__file__).parent.parent
    env_file = root / ".env"

    if not env_file.exists():
        return False

    with open(env_file) as f:
        content = f.read()

    # Проверяем placeholder значения
    placeholders = [
        'your_bot_token_here',
        'your_chat_id_here',
        'your_openrouter_key_here',
        'your-binom-tracker-url.com',
        'your_binom_api_key_here',
    ]

    found_placeholders = []
    for placeholder in placeholders:
        if placeholder in content:
            found_placeholders.append(placeholder)

    if found_placeholders:
        print("\nWARNING: .env содержит placeholder значения:")
        for placeholder in found_placeholders:
            print(f"  - {placeholder}")
        return False

    return True


def check_python_version():
    """
    Проверяет версию Python
    """
    if sys.version_info < (3, 10):
        print("ОШИБКА: Требуется Python 3.10 или выше")
        print(f"Текущая версия: {sys.version}")
        return False
    return True


def create_data_dirs():
    """
    Создает необходимые директории для данных
    """
    root = Path(__file__).parent.parent

    dirs = [
        root / "data",
        root / "logs",
        root / "data" / "cache",
        root / "data" / "exports"
    ]

    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

        # Создаем .gitkeep в пустых папках
        gitkeep = dir_path / ".gitkeep"
        if not any(dir_path.iterdir()):
            gitkeep.touch()

    print("Созданы директории для данных и логов")


def main():
    """
    Главная функция настройки
    """
    print("=" * 60)
    print("Binom Assistant - Первоначальная настройка")
    print("=" * 60)

    # Проверка версии Python
    if not check_python_version():
        return 1

    # Создание директорий
    create_data_dirs()

    # Создание .env файла
    create_env_file()

    print("\n" + "=" * 60)
    print("Настройка завершена!")
    print("=" * 60)
    print("\nСледующие шаги:")
    print("1. Отредактируй файл .env и заполни свои данные")
    print("2. Установи зависимости: pip install -r requirements.txt")
    print("3. Запусти проект: python main.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
