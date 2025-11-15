"""
SettingsManager - сервис для управления настройками приложения

Приоритет значений (cascading):
1. БД (app_settings) - если есть запись
2. .env файл - если нет в БД
3. Hardcoded defaults - если нигде нет

Использование:
    from services.settings_manager import SettingsManager

    settings = SettingsManager()
    days = settings.get('collector.update_days', default=7)
    settings.set('collector.update_days', 14)
"""

import logging
import time
from typing import Any, Dict, Optional, List

from config.config import get_config
from storage.database import session_scope, AppSettings

logger = logging.getLogger(__name__)


class SettingsManager:
    """
    Менеджер настроек приложения с каскадным fallback:
    БД -> .env -> defaults
    """

    def __init__(self):
        """Инициализация менеджера настроек"""
        self.config = get_config()
        self._cache = {}  # Кэш для частых запросов
        self._cache_timestamps = {}  # Timestamps для TTL
        self._cache_ttl = 60  # TTL в секундах
        logger.debug("SettingsManager инициализирован")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение настройки с fallback логикой

        Приоритет:
        1. БД (app_settings)
        2. .env файл (через Config)
        3. Переданный default

        Args:
            key: ключ настройки (например, 'collector.update_days')
            default: значение по умолчанию

        Returns:
            Значение настройки правильного типа
        """
        # Проверяем кэш
        if key in self._cache:
            # Проверяем TTL
            cache_age = time.time() - self._cache_timestamps.get(key, 0)
            if cache_age < self._cache_ttl:
                logger.debug(f"Settings cache hit: {key} = {self._cache[key]} (age: {cache_age:.1f}s)")
                return self._cache[key]
            else:
                # TTL истек - удаляем из кэша
                logger.debug(f"Settings cache expired for {key} (age: {cache_age:.1f}s)")
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)

        try:
            # 1. Ищем в БД
            with session_scope() as session:
                setting = session.query(AppSettings).filter_by(key=key).first()

                if setting:
                    value = setting.get_typed_value()
                    self._cache[key] = value
                    self._cache_timestamps[key] = time.time()
                    logger.debug(f"Settings from DB: {key} = {value}")
                    return value

            # 2. Ищем в .env (через Config)
            env_value = self.config.get(key)
            if env_value is not None:
                self._cache[key] = env_value
                self._cache_timestamps[key] = time.time()
                logger.debug(f"Settings from .env: {key} = {env_value}")
                return env_value

            # 3. Возвращаем default
            logger.debug(f"Settings from default: {key} = {default}")
            return default

        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default

    def set(self, key: str, value: Any, value_type: Optional[str] = None,
            category: Optional[str] = None, description: Optional[str] = None) -> bool:
        """
        Сохраняет значение настройки в БД

        Args:
            key: ключ настройки
            value: значение
            value_type: тип ('int', 'float', 'bool', 'string', 'json')
            category: категория настройки
            description: описание

        Returns:
            True если сохранено успешно
        """
        try:
            # Определяем тип автоматически если не указан
            if value_type is None:
                if isinstance(value, bool):
                    value_type = 'bool'
                elif isinstance(value, int):
                    value_type = 'int'
                elif isinstance(value, float):
                    value_type = 'float'
                else:
                    value_type = 'string'

            # Конвертируем значение в строку
            value_str = str(value).lower() if isinstance(value, bool) else str(value)

            with session_scope() as session:
                setting = session.query(AppSettings).filter_by(key=key).first()

                if setting:
                    # Обновляем существующую
                    setting.value = value_str
                    if value_type:
                        setting.value_type = value_type
                    logger.info(f"Settings updated: {key} = {value}")
                else:
                    # Создаем новую
                    if not category:
                        # Пытаемся определить категорию из ключа
                        category = key.split('.')[0] if '.' in key else 'general'

                    setting = AppSettings(
                        key=key,
                        value=value_str,
                        value_type=value_type,
                        category=category,
                        description=description
                    )
                    session.add(setting)
                    logger.info(f"Settings created: {key} = {value}")

                session.commit()

                # Очищаем кэш для этого ключа
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)

                return True

        except Exception as e:
            logger.error(f"Error setting {key} = {value}: {e}")
            return False

    def get_all(self) -> Dict[str, Any]:
        """
        Получает все настройки из БД

        Returns:
            Словарь {key: value} со всеми настройками
        """
        try:
            with session_scope() as session:
                settings = session.query(AppSettings).all()
                return {s.key: s.get_typed_value() for s in settings}
        except Exception as e:
            logger.error(f"Error getting all settings: {e}")
            return {}

    def get_category(self, category: str) -> Dict[str, Any]:
        """
        Получает все настройки определенной категории

        Args:
            category: категория ('collector', 'schedule', 'filters', etc)

        Returns:
            Словарь {key: value} с настройками категории
        """
        try:
            with session_scope() as session:
                settings = session.query(AppSettings).filter_by(category=category).all()
                return {s.key: s.get_typed_value() for s in settings}
        except Exception as e:
            logger.error(f"Error getting category {category}: {e}")
            return {}

    def get_category_details(self, category: str) -> List[Dict]:
        """
        Получает детальную информацию о настройках категории
        (включая описание, min/max, editable, etc)

        Args:
            category: категория настроек

        Returns:
            Список словарей с полной информацией о настройках
        """
        try:
            with session_scope() as session:
                settings = session.query(AppSettings).filter_by(category=category).all()
                return [s.to_dict() for s in settings]
        except Exception as e:
            logger.error(f"Error getting category details {category}: {e}")
            return []

    def reset(self, key: str) -> bool:
        """
        Удаляет настройку из БД (fallback на .env или default)

        Args:
            key: ключ настройки

        Returns:
            True если удалено успешно
        """
        try:
            with session_scope() as session:
                setting = session.query(AppSettings).filter_by(key=key).first()
                if setting:
                    session.delete(setting)
                    session.commit()
                    logger.info(f"Settings reset: {key}")

                    # Очищаем кэш
                    self._cache.pop(key, None)
                    self._cache_timestamps.pop(key, None)

                    return True
                return False
        except Exception as e:
            logger.error(f"Error resetting {key}: {e}")
            return False

    def clear_cache(self):
        """Очищает кэш настроек"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.debug("Settings cache cleared")

    def migrate_from_env(self, keys: List[str]) -> int:
        """
        Мигрирует настройки из .env в БД

        Args:
            keys: список ключей для миграции

        Returns:
            Количество мигрированных настроек
        """
        migrated = 0

        for key in keys:
            try:
                # Проверяем, есть ли уже в БД
                with session_scope() as session:
                    existing = session.query(AppSettings).filter_by(key=key).first()
                    if existing:
                        logger.debug(f"Skip migration {key}: already in DB")
                        continue

                # Читаем из .env
                env_value = self.config.get(key)
                if env_value is not None:
                    # Сохраняем в БД
                    if self.set(key, env_value):
                        migrated += 1
                        logger.info(f"Migrated {key} = {env_value} from .env to DB")

            except Exception as e:
                logger.error(f"Error migrating {key}: {e}")

        return migrated


# Singleton instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """
    Получает синглтон SettingsManager

    Returns:
        SettingsManager: экземпляр менеджера настроек
    """
    global _settings_manager

    if _settings_manager is None:
        _settings_manager = SettingsManager()
        logger.info("SettingsManager singleton created")

    return _settings_manager
