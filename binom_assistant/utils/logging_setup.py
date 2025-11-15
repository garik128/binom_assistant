"""
Централизованная настройка логирования для всех скриптов и модулей
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(level=logging.INFO, log_file=None, console=True):
    """
    Настраивает логирование приложения в файл и/или консоль.

    Args:
        level: Уровень логирования (по умолчанию INFO)
        log_file: Путь к файлу логов (если None, используется logs/app.log)
        console: Выводить логи в консоль (по умолчанию True)

    Returns:
        Logger объект для использования в скрипте
    """
    # Определяем корневую папку проекта
    root_dir = Path(__file__).parent.parent
    log_dir = root_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    # Используем переданный путь или дефолтный
    if log_file is None:
        log_file = log_dir / "app.log"
    else:
        log_file = Path(log_file)

    # Настраиваем формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Создаем корневой logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Удаляем существующие handlers чтобы избежать дублирования
    root_logger.handlers.clear()

    # File handler с ротацией (макс 10MB, 5 бэкапов)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(file_handler)

    # Console handler (опционально)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        root_logger.addHandler(console_handler)

    # Возвращаем logger для использования
    return logging.getLogger(__name__)
