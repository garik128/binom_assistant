"""
Упрощённый модуль для работы с конфигурацией через .env
"""
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class Config:
    """
    Класс для работы с конфигурацией проекта.
    Загружает настройки из .env файла.
    """

    def __init__(self):
        """Инициализация конфигурации"""
        # Определяем корневую папку проекта
        self.root_dir = Path(__file__).parent.parent

        # Загружаем переменные окружения из .env
        env_file = self.root_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logger.info(f"Загружены переменные из {env_file}")
        else:
            logger.warning(f".env файл не найден: {env_file}")

        # Валидация критических параметров
        self._validate_required_config()

    def get(self, path: str, default: Any = None) -> Any:
        """
        Получает значение из переменных окружения.

        Примеры:
            config.get("binom.url") -> os.getenv("BINOM_URL")
            config.get("telegram.chat_id") -> os.getenv("TELEGRAM_CHAT_ID")

        Args:
            path: путь к значению (маппится на переменную окружения)
            default: значение по умолчанию

        Returns:
            Значение из .env или default
        """
        # Маппинг путей на переменные окружения
        env_map = {
            # Binom
            "binom.url": "BINOM_URL",
            "binom.api_key": "BINOM_API_KEY",

            # Telegram
            "telegram.bot_token": "TELEGRAM_BOT_TOKEN",
            "telegram.chat_id": "TELEGRAM_CHAT_ID",

            # OpenRouter
            "openrouter.api_key": "OPENROUTER_API_KEY",
            "openrouter.model": ("OPENROUTER_MODEL", "openai/gpt-4.1-mini"),
            "openrouter.max_tokens": ("OPENROUTER_MAX_TOKENS", "16000"),  # Увеличено для работы с DB tools
            "openrouter.context_messages": ("OPENROUTER_CONTEXT_MESSAGES", "10"),

            # Database
            "database.url": ("DATABASE_URL", "sqlite:///./data/binom_assistant.db"),

            # App
            "app.environment": ("ENVIRONMENT", "development"),
            "app.debug": ("DEBUG", "true"),
            "app.log_level": ("LOG_LEVEL", "INFO"),

            # Collector
            "collector.enabled": ("COLLECTOR_ENABLED", "true"),
            "collector.interval_hours": ("COLLECTOR_INTERVAL_HOURS", "24"),
            "collector.update_days": ("COLLECTOR_UPDATE_DAYS", "7"),
            "collector.api_pause": ("COLLECTOR_API_PAUSE", "3.0"),

            # Timezone
            "app.timezone": ("TIMEZONE", "Europe/Moscow"),

            # Auth
            "auth.username": ("AUTH_USERNAME", "admin"),
            "auth.password": ("AUTH_PASSWORD", "admin"),
            "auth.jwt_secret": ("AUTH_JWT_SECRET", ""),
            "auth.jwt_algorithm": ("AUTH_JWT_ALGORITHM", "HS256"),
            "auth.jwt_expiration_minutes": ("AUTH_JWT_EXPIRATION_MINUTES", "1440"),

            # CORS
            "cors.origins": ("CORS_ORIGINS", "*"),
        }

        mapping = env_map.get(path)

        if mapping is None:
            return default

        # Если mapping это tuple - первый элемент переменная, второй - дефолт
        if isinstance(mapping, tuple):
            env_var, env_default = mapping
            value = os.getenv(env_var, env_default)
        else:
            env_var = mapping
            value = os.getenv(env_var, default)

        # Пытаемся конвертировать в число если возможно
        if isinstance(value, str):
            if value.lower() in ('true', 'false'):
                return value.lower() == 'true'
            try:
                if '.' in value:
                    return float(value)
                return int(value)
            except ValueError:
                return value

        return value

    def get_section(self, section: str) -> Dict:
        """
        Получает целую секцию конфига.

        Args:
            section: имя секции (например, "binom", "telegram")

        Returns:
            Словарь с настройками секции
        """
        sections = {
            "binom": {
                "url": self.get("binom.url"),
                "api_key": self.get("binom.api_key"),
            },
            "telegram": {
                "bot_token": self.get("telegram.bot_token"),
                "chat_id": self.get("telegram.chat_id"),
            },
            "openrouter": {
                "api_key": self.get("openrouter.api_key"),
                "model": self.get("openrouter.model"),
                "max_tokens": int(self.get("openrouter.max_tokens")),  # Преобразуем в int для API
                "context_messages": int(self.get("openrouter.context_messages")),  # Преобразуем в int
            },
            "database": {
                "url": self.get("database.url"),
            },
            "app": {
                "environment": self.get("app.environment"),
                "debug": self.get("app.debug"),
                "log_level": self.get("app.log_level"),
                "timezone": self.get("app.timezone"),
            },
            "collector": {
                "enabled": self.get("collector.enabled"),
                "interval_hours": self.get("collector.interval_hours"),
                "update_days": self.get("collector.update_days"),
            },
            "auth": {
                "username": self.get("auth.username"),
                "password": self.get("auth.password"),
                "jwt_secret": self.get("auth.jwt_secret"),
                "jwt_algorithm": self.get("auth.jwt_algorithm"),
                "jwt_expiration_minutes": self.get("auth.jwt_expiration_minutes"),
            },
        }

        return sections.get(section, {})

    def _validate_required_config(self):
        """
        Валидирует критическую конфигурацию при запуске.

        Raises:
            ValueError: Если обязательные параметры отсутствуют или невалидны
        """
        errors = []

        # Проверка Binom URL
        binom_url = self.get("binom.url", "")
        if not binom_url:
            errors.append("BINOM_URL is required")
        elif not binom_url.startswith(('http://', 'https://')):
            errors.append("BINOM_URL must start with http:// or https://")

        # Проверка Binom API Key
        if not self.get("binom.api_key", ""):
            errors.append("BINOM_API_KEY is required")

        # Логируем ошибки или успех
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            logger.info("Configuration validated successfully")

    # Свойства для обратной совместимости
    @property
    def binom_url(self) -> str:
        return self.get("binom.url", "")

    @property
    def binom_api_key(self) -> str:
        return self.get("binom.api_key", "")

    @property
    def database_url(self) -> str:
        db_url = self.get("database.url", "sqlite:///./data/binom_assistant.db")

        # Обрабатываем только SQLite URLs
        if not db_url.startswith("sqlite:///"):
            return db_url  # Другие типы БД или уже абсолютный путь

        # Извлекаем путь после sqlite:///
        path = db_url.replace("sqlite:///", "")

        # Если относительный путь (начинается с ./ или не начинается с /)
        if path.startswith("./") or (not path.startswith("/") and not (len(path) > 1 and path[1] == ':')):
            path = path.lstrip("./")
            absolute_path = self.root_dir / path
            db_url = f"sqlite:///{absolute_path}"

            # Убеждаемся что директория существует
            db_file = Path(absolute_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Database directory ensured: {db_file.parent}")

        return db_url

    @property
    def environment(self) -> str:
        return self.get("app.environment", "development")

    @property
    def debug(self) -> bool:
        return self.get("app.debug", True)

    @property
    def timezone(self) -> str:
        """Возвращает название timezone (например, 'Europe/Moscow')"""
        return self.get("app.timezone", "Europe/Moscow")

    def get_timezone(self) -> ZoneInfo:
        """
        Возвращает timezone объект для использования с datetime.

        Returns:
            ZoneInfo объект настроенной timezone
        """
        try:
            return ZoneInfo(self.timezone)
        except Exception as e:
            logger.warning(f"Invalid timezone '{self.timezone}', using Europe/Moscow: {e}")
            return ZoneInfo("Europe/Moscow")

    def get_timezone_offset(self) -> str:
        """
        Возвращает timezone offset для Binom API в формате '+HH:MM' или '-HH:MM'.
        Офсет фиксируется при инициализации конфига.

        Returns:
            str: Timezone offset (например, '+3:00', '-5:00')
        """
        from datetime import datetime

        try:
            tz = self.get_timezone()
            # Получаем текущий offset для данной timezone
            now = datetime.now(tz)
            offset = now.utcoffset()

            if offset is None:
                logger.warning("Could not determine timezone offset, using '+3:00'")
                return '+3:00'

            # Конвертируем offset в секунды, затем в часы и минуты
            total_seconds = int(offset.total_seconds())
            hours = total_seconds // 3600
            minutes = (abs(total_seconds) % 3600) // 60

            # Форматируем в +HH:MM или -HH:MM
            sign = '+' if hours >= 0 else '-'
            return f"{sign}{abs(hours)}:{minutes:02d}"

        except Exception as e:
            logger.warning(f"Error calculating timezone offset: {e}, using '+3:00'")
            return '+3:00'


# Singleton instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """
    Получает синглтон конфигурации.

    Returns:
        Config: Экземпляр конфигурации
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = Config()
        logger.info("Конфигурация инициализирована")

    return _config_instance


def reload_config():
    """Перезагружает конфигурацию"""
    global _config_instance
    _config_instance = None
    return get_config()
