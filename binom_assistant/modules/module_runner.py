"""
Запуск и управление модулями
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
from contextlib import contextmanager

from storage.database.base import get_session
from storage.database.models import (
    ModuleConfig as ModuleConfigDB,
    ModuleRun as ModuleRunDB,
    ModuleCache as ModuleCacheDB
)
from .base_module import BaseModule, ModuleConfig, ModuleResult
from .registry import get_registry

logger = logging.getLogger(__name__)


@contextmanager
def get_db_session():
    """
    Локальная обертка над get_session() для использования в with.
    Преобразует генератор в контекстный менеджер.

    НЕ ТРОГАТЬ storage/database/base.py - он работает правильно!
    """
    session_gen = get_session()
    session = next(session_gen)
    try:
        yield session
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


class ModuleRunner:
    """
    Запускает модули и управляет их состоянием.

    Возможности:
    - Запуск модулей по ID
    - Кэширование результатов
    - Сохранение истории запусков
    - Загрузка конфигурации из БД
    """

    def __init__(self):
        self.registry = get_registry()
        logger.info("ModuleRunner initialized")

    def run_module(
        self,
        module_id: str,
        config: Optional[ModuleConfig] = None,
        use_cache: bool = True
    ) -> ModuleResult:
        """
        Запускает модуль по ID.

        Args:
            module_id: ID модуля
            config: Конфигурация (опционально)
            use_cache: Использовать кэш

        Returns:
            ModuleResult: Результат выполнения

        Raises:
            ValueError: Если модуль не найден
        """
        # Получаем модуль из реестра
        module = self.registry.get_module_instance(module_id)
        if not module:
            raise ValueError(f"Module '{module_id}' not found in registry")

        # Загружаем конфигурацию из БД если не передана
        if config is None:
            config = self._load_config(module_id) or module.config

        # Проверяем кэш
        if use_cache:
            cached_result = self._get_from_cache(module, config)
            if cached_result:
                logger.info(f"Module '{module_id}' result loaded from cache")
                return cached_result

        # Запускаем модуль
        logger.info(f"Running module '{module_id}'...")
        result = module.run(config)
        logger.info(f"Module '{module_id}' completed with status: {result.status}")

        # Сохраняем результат в БД (с параметрами)
        run_id = self._save_run(result, config.params)

        # Отправляем алерты в Telegram если есть
        if result.status == "success":
            self._send_alerts_to_telegram(module_id, result, run_id)

        # Кэшируем результат если успешно
        if result.status == "success" and use_cache:
            self._save_to_cache(module, config, result)

        return result

    def _load_config(self, module_id: str) -> Optional[ModuleConfig]:
        """
        Загружает конфигурацию модуля из БД.

        Args:
            module_id: ID модуля

        Returns:
            Optional[ModuleConfig]: Конфигурация или None
        """
        try:
            with get_db_session() as session:
                db_config = session.query(ModuleConfigDB).filter(
                    ModuleConfigDB.module_id == module_id
                ).first()

                if db_config:
                    return ModuleConfig(
                        enabled=db_config.enabled,
                        schedule=db_config.schedule,
                        alerts_enabled=getattr(db_config, 'alerts_enabled', False),
                        timeout_seconds=db_config.timeout_seconds,
                        cache_ttl_seconds=db_config.cache_ttl_seconds,
                        params=db_config.params or {}
                    )
        except Exception as e:
            logger.error(f"Error loading config for module '{module_id}': {e}")

        return None

    def _save_run(self, result: ModuleResult, params: dict = None) -> int:
        """
        Сохраняет результат запуска в БД.

        Args:
            result: Результат выполнения модуля
            params: Параметры запуска модуля

        Returns:
            ID сохраненной записи
        """
        import time
        from sqlalchemy.exc import OperationalError

        # Retry логика для SQLite "database is locked"
        # Когда много модулей запускаются одновременно, может быть конкуренция за блокировку БД
        max_retries = 3
        retry_delay = 1  # секунда

        for attempt in range(max_retries):
            try:
                with get_db_session() as session:
                    run = ModuleRunDB(
                        module_id=result.module_id,
                        started_at=result.started_at,
                        completed_at=result.completed_at,
                        status=result.status,
                        results=result.model_dump(mode='json') if result.status == "success" else None,
                        params=params,  # сохраняем параметры запуска
                        error=result.error,
                        execution_time_ms=result.execution_time_ms
                    )
                    session.add(run)
                    session.commit()
                    session.refresh(run)  # Обновляем чтобы получить ID
                    logger.info(f"Run saved for module '{result.module_id}' with params: {params}, run_id: {run.id}")
                    return run.id

            except OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked for module '{result.module_id}', retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Экспоненциальная задержка
                else:
                    logger.error(f"Error saving run for module '{result.module_id}': {e}")
                    return None
            except Exception as e:
                logger.error(f"Error saving run for module '{result.module_id}': {e}")
                return None

        return None

    def _send_alerts_to_telegram(self, module_id: str, result: ModuleResult, run_id: int = None) -> None:
        """
        Отправляет алерты в Telegram если модуль включен в настройках.

        Args:
            module_id: ID модуля
            result: Результат выполнения модуля
            run_id: ID запуска модуля в БД (не используется)
        """
        try:
            # Получаем алерты из результата
            alerts = result.alerts if hasattr(result, 'alerts') else []

            if not alerts:
                logger.debug(f"No alerts to send for module '{module_id}'")
                return

            # Импортируем сервис отправки
            from services.telegram_alert_sender import get_telegram_alert_sender

            sender = get_telegram_alert_sender()
            sender.send_alerts(module_id, alerts)

        except Exception as e:
            # Не падаем если отправка не удалась
            logger.error(f"Error sending alerts to Telegram for module '{module_id}': {e}")

    def _get_from_cache(
        self,
        module: BaseModule,
        config: ModuleConfig
    ) -> Optional[ModuleResult]:
        """
        Получает результат из кэша.

        Args:
            module: Экземпляр модуля
            config: Конфигурация

        Returns:
            Optional[ModuleResult]: Результат из кэша или None
        """
        cache_key = module.get_cache_key(config)

        try:
            with get_db_session() as session:
                cache_entry = session.query(ModuleCacheDB).filter(
                    ModuleCacheDB.module_id == module.metadata.id,
                    ModuleCacheDB.cache_key == cache_key,
                    ModuleCacheDB.expires_at > datetime.now()
                ).first()

                if cache_entry and cache_entry.data:
                    return ModuleResult(**cache_entry.data)
        except Exception as e:
            logger.error(f"Error reading cache for module '{module.metadata.id}': {e}")

        return None

    def _save_to_cache(
        self,
        module: BaseModule,
        config: ModuleConfig,
        result: ModuleResult
    ) -> None:
        """
        Сохраняет результат в кэш.

        Args:
            module: Экземпляр модуля
            config: Конфигурация
            result: Результат выполнения
        """
        cache_key = module.get_cache_key(config)
        expires_at = datetime.now() + timedelta(seconds=config.cache_ttl_seconds)

        try:
            with get_db_session() as session:
                # Удаляем старую запись если есть
                session.query(ModuleCacheDB).filter(
                    ModuleCacheDB.module_id == module.metadata.id,
                    ModuleCacheDB.cache_key == cache_key
                ).delete()

                # Создаем новую
                cache_entry = ModuleCacheDB(
                    module_id=module.metadata.id,
                    cache_key=cache_key,
                    data=result.model_dump(mode='json'),
                    expires_at=expires_at
                )
                session.add(cache_entry)
                session.commit()
                logger.info(f"Result cached for module '{module.metadata.id}'")
        except Exception as e:
            logger.error(f"Error saving cache for module '{module.metadata.id}': {e}")

    def clear_cache(self, module_id: Optional[str] = None) -> int:
        """
        Очищает кэш модулей.

        Args:
            module_id: ID модуля (опционально, если None - очищает весь кэш)

        Returns:
            int: Количество удаленных записей
        """
        try:
            with get_db_session() as session:
                query = session.query(ModuleCacheDB)

                if module_id:
                    query = query.filter(ModuleCacheDB.module_id == module_id)

                count = query.delete()
                session.commit()
                logger.info(f"Cleared {count} cache entries")
                return count
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0

    def clear_expired_cache(self) -> int:
        """
        Очищает просроченные записи кэша.

        Returns:
            int: Количество удаленных записей
        """
        try:
            with get_db_session() as session:
                count = session.query(ModuleCacheDB).filter(
                    ModuleCacheDB.expires_at <= datetime.now()
                ).delete()
                session.commit()
                logger.info(f"Cleared {count} expired cache entries")
                return count
        except Exception as e:
            logger.error(f"Error clearing expired cache: {e}")
            return 0
