"""
Утилиты для работы с timezone-aware datetime

Все функции возвращают datetime с учетом timezone из конфигурации.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional


_cached_timezone: Optional[ZoneInfo] = None


def get_timezone() -> ZoneInfo:
    """
    Получает timezone из конфигурации с обработкой ошибок.

    Использует кэширование для производительности.
    В случае ошибки использует Europe/Moscow как fallback.

    Returns:
        ZoneInfo объект настроенной timezone
    """
    global _cached_timezone
    import logging
    logger = logging.getLogger(__name__)

    if _cached_timezone is None:
        try:
            from config import get_config
            config = get_config()
            _cached_timezone = config.get_timezone()
        except Exception as e:
            logger.error(f"Failed to load timezone from config: {e}")
            logger.warning("Falling back to Europe/Moscow")
            _cached_timezone = ZoneInfo("Europe/Moscow")

    return _cached_timezone


def get_now() -> datetime:
    """
    Возвращает текущее время с timezone из конфигурации.

    Использует вместо datetime.now() для получения timezone-aware datetime.

    Returns:
        datetime с timezone

    Example:
        >>> from utils import get_now
        >>> now = get_now()
        >>> print(now.tzinfo)  # Europe/Moscow
    """
    tz = get_timezone()
    return datetime.now(tz)


def reset_timezone_cache():
    """
    Сбрасывает кэш timezone.

    Используется при изменении конфигурации или в тестах.
    """
    global _cached_timezone
    _cached_timezone = None
