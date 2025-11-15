"""
Скрипт для запуска веб-интерфейса (без полноценного пакета)
Обходной вариант для локальной разработки
"""
import sys
import os
from pathlib import Path

# Добавляем корневую папку проекта в PYTHONPATH
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Создаём переменную окружения для указания на корень проекта
os.environ['BINOM_ASSISTANT_ROOT'] = str(ROOT_DIR)

if __name__ == "__main__":
    print("=" * 60)
    print("Запуск Binom Assistant Web Interface")
    print("=" * 60)
    print()
    print("Адрес: http://0.0.0.0:8000")
    print("API Документация: http://0.0.0.0:8000/docs")
    print("ReDoc: http://0.0.0.0:8000/redoc")
    print()
    print("Нажмите Ctrl+C для остановки")
    print("=" * 60)
    print()

    # Настройка логирования в файл
    try:
        from utils.logging_setup import setup_logging
        setup_logging()
        print("[OK] Логирование настроено (logs/app.log)")
    except Exception as e:
        print(f"[WARN] Не удалось настроить file logging: {e}")

    # Попытка импорта - покажет где проблема
    try:
        print("Попытка загрузки модулей...")
        from interfaces.web.main import app
        print("[OK] Модули загружены успешно")
        print()

        import uvicorn
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info"
        )
    except ImportError as e:
        print(f"[ERROR] Ошибка импорта: {e}")
        print()
        print("Возможное решение:")
        print("1. Проверьте, что все зависимости установлены")
        print("2. Убедитесь, что в файлах используются относительные импорты")
        print("3. Или запустите через: python -m interfaces.web.main")
        sys.exit(1)
