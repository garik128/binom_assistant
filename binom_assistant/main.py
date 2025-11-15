"""
Binom Assistant - Главный файл запуска веб-сервера

Использование:
    python main.py                    # Запуск в production режиме
    python main.py --dev              # Запуск в development режиме (с hot reload)
    python main.py --host 0.0.0.0     # Указать хост
    python main.py --port 8000        # Указать порт
"""
import sys
import argparse
import uvicorn
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Добавляем корневую папку в путь
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))


def setup_logging():
    """
    Настраивает логирование приложения в файл и консоль
    """
    # Создаем директорию для логов если её нет
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "app.log"

    # Настраиваем формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Создаем корневой logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Удаляем существующие handlers чтобы избежать дублирования
    root_logger.handlers.clear()

    # File handler с ротацией (макс 10MB, 5 бэкапов)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Добавляем handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Логируем старт
    logger = logging.getLogger(__name__)
    logger.info("Binom Assistant запущен")
    logger.info("=" * 60)
    logger.info("Инициализация системы...")

    return logger


def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Binom Assistant Web Server')
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to bind (default: 8000)'
    )
    parser.add_argument(
        '--dev',
        action='store_true',
        help='Development mode with hot reload'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Number of worker processes (production only)'
    )
    return parser.parse_args()


def main():
    """
    Главная функция запуска
    """
    args = parse_args()

    # Настраиваем логирование
    logger = setup_logging()

    # Валидируем конфигурацию
    try:
        from config import get_config
        config_obj = get_config()
        logger.info(f"Config loaded: environment={config_obj.environment}")
        logger.info(f"Database: {config_obj.database_url}")
        logger.info(f"Binom URL: {config_obj.binom_url}")
        # НЕ логируем API ключи!
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        print(f"\nERROR: Configuration validation failed!")
        print(f"Details: {e}")
        print("\nPlease check your .env file and ensure all required variables are set.")
        return 1

    print("=" * 60)
    print("Binom Assistant - Web Server")
    print("=" * 60)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Mode: {'Development (Hot Reload)' if args.dev else 'Production'}")
    print("=" * 60)

    logger.info("Система успешно инициализирована")
    logger.info("Приложение готово к работе")

    # Конфигурация uvicorn
    config = {
        "app": "interfaces.web.main:app",
        "host": args.host,
        "port": args.port,
    }

    if args.dev:
        # Development режим
        config.update({
            "reload": True,
            "log_level": "debug",
        })
    else:
        # Production режим
        config.update({
            "workers": args.workers,
            "log_level": "info",
        })

    try:
        uvicorn.run(**config)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
