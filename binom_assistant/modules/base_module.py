"""
Базовый класс для всех модулей аналитики
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import logging
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)


class ModuleTimeoutException(Exception):
    """Исключение при превышении таймаута выполнения модуля"""
    pass


class ModuleMetadata(BaseModel):
    """Метаданные модуля"""
    id: str = Field(..., description="Уникальный ID модуля (bleeding_detector)")
    name: str = Field(..., description="Человекочитаемое название")
    category: str = Field(..., description="Категория модуля")
    description: str = Field(..., description="Краткое описание модуля (1-2 предложения)")
    detailed_description: Optional[str] = Field(default=None, description="Подробное описание для вкладки 'О модуле'")
    version: str = Field(default="1.0.0", description="Версия модуля")
    author: str = Field(default="Binom Assistant", description="Автор модуля")
    priority: str = Field(default="medium", description="Приоритет: low, medium, high, critical")
    tags: List[str] = Field(default_factory=list, description="Теги для поиска")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "bleeding_detector",
                "name": "Bleeding Campaign Detector",
                "category": "critical_alerts",
                "description": "Находит критически убыточные кампании",
                "version": "1.0.0",
                "author": "Binom Assistant",
                "priority": "critical",
                "tags": ["roi", "losses", "critical"]
            }
        }


class ModuleConfig(BaseModel):
    """Конфигурация модуля"""
    enabled: bool = Field(default=True, description="Модуль включен")
    schedule: Optional[str] = Field(default=None, description="Cron expression для автозапуска")
    alerts_enabled: bool = Field(default=False, description="Генерация алертов в Telegram")
    timeout_seconds: int = Field(default=30, description="Таймаут выполнения в секундах")
    cache_ttl_seconds: int = Field(default=3600, description="Время жизни кэша в секундах")
    params: Dict[str, Any] = Field(default_factory=dict, description="Параметры модуля")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "schedule": "0 */6 * * *",
                "alerts_enabled": False,
                "timeout_seconds": 30,
                "cache_ttl_seconds": 3600,
                "params": {
                    "roi_threshold": -50,
                    "min_spend": 5,
                    "days": 3
                }
            }
        }


class ModuleResult(BaseModel):
    """Результат выполнения модуля"""
    module_id: str
    status: str = Field(..., description="Статус: success, error, timeout")
    started_at: datetime
    completed_at: datetime
    execution_time_ms: int
    data: Dict[str, Any] = Field(default_factory=dict, description="Основные данные")
    charts: List[Dict[str, Any]] = Field(default_factory=list, description="Данные для графиков")
    recommendations: List[str] = Field(default_factory=list, description="Рекомендации")
    alerts: List[Dict[str, Any]] = Field(default_factory=list, description="Критические алерты")
    error: Optional[str] = Field(default=None, description="Сообщение об ошибке")

    class Config:
        json_schema_extra = {
            "example": {
                "module_id": "bleeding_detector",
                "status": "success",
                "started_at": "2025-10-27T10:00:00",
                "completed_at": "2025-10-27T10:00:05",
                "execution_time_ms": 5000,
                "data": {"campaigns": [], "summary": {}},
                "charts": [],
                "recommendations": [],
                "alerts": [],
                "error": None
            }
        }


class BaseModule(ABC):
    """
    Базовый класс для всех модулей аналитики.

    Архитектура:
    - Синхронная работа (соответствует архитектуре проекта)
    - SQLAlchemy для работы с БД
    - Pydantic для валидации схем
    - Логирование через logging

    Пример использования:
        module = BleedingCampaignDetector()
        result = module.run()
        print(result.data)
    """

    def __init__(self):
        self.metadata = self.get_metadata()
        self.config = self.get_default_config()
        logger.info(f"Module '{self.metadata.id}' initialized")

    @abstractmethod
    def get_metadata(self) -> ModuleMetadata:
        """
        Возвращает метаданные модуля.

        Returns:
            ModuleMetadata: Метаданные модуля
        """
        pass

    @abstractmethod
    def get_default_config(self) -> ModuleConfig:
        """
        Возвращает конфигурацию по умолчанию.

        Returns:
            ModuleConfig: Конфигурация модуля
        """
        pass

    @abstractmethod
    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Основная логика анализа.

        Работает с БД через SQLAlchemy:
        ```python
        from storage.database.base import session_scope
        from storage.database.models import CampaignStatsDaily

        with session_scope() as session:
            stats = session.query(CampaignStatsDaily).filter(...).all()
        ```

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Сырые данные для дальнейшей обработки
        """
        pass

    def validate_config(self, config: ModuleConfig) -> bool:
        """
        Валидация конфигурации модуля.

        Args:
            config: Конфигурация для проверки

        Returns:
            bool: True если конфигурация валидна
        """
        return True

    def format_results(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Форматирование результатов для UI.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            Dict[str, Any]: Отформатированные данные
        """
        return raw_data

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Подготовка данных для Chart.js.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            List[Dict[str, Any]]: Список графиков в формате Chart.js
        """
        return []

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций на основе анализа.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            List[str]: Список рекомендаций
        """
        return []

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            List[Dict[str, Any]]: Список алертов
        """
        return []

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.
        Переопределяется в дочерних классах при необходимости.

        Returns:
            Dict с описаниями параметров
        """
        return {}

    def get_severity_metadata(self) -> Dict[str, Any]:
        """
        Возвращает метаданные для настройки порогов severity.
        Переопределяется в модулях, использующих severity.

        Returns:
            Dict с метаданными severity thresholds
        """
        return {}

    def get_cache_key(self, config: ModuleConfig) -> str:
        """
        Генерирует ключ кэша на основе конфигурации и версии модуля.

        Args:
            config: Конфигурация модуля

        Returns:
            str: Хэш-ключ для кэша
        """
        # Сериализуем params для создания уникального ключа
        params_str = json.dumps(config.params, sort_keys=True)
        # ВАЖНО: включаем версию модуля в ключ кэша!
        # При изменении кода модуля нужно обновить версию в metadata
        hash_input = f"{self.metadata.id}_{self.metadata.version}_{params_str}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _run_with_timeout(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Внутренний метод для выполнения анализа с таймаутом.
        Вызывается из run() через ThreadPoolExecutor.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict с результатами: raw_data, formatted_data, charts, recommendations, alerts
        """
        # Выполнить анализ
        raw_data = self.analyze(config)

        # Обработать результаты
        formatted_data = self.format_results(raw_data)
        charts = self.prepare_chart_data(raw_data)
        recommendations = self.generate_recommendations(raw_data)

        # Генерировать алерты только если включено в конфиге
        if config.alerts_enabled:
            alerts = self.generate_alerts(raw_data)
        else:
            alerts = []

        return {
            'raw_data': raw_data,
            'formatted_data': formatted_data,
            'charts': charts,
            'recommendations': recommendations,
            'alerts': alerts
        }

    def run(self, config: Optional[ModuleConfig] = None) -> ModuleResult:
        """
        Главный метод запуска модуля с enforcement таймаута.

        Args:
            config: Конфигурация модуля (опционально)

        Returns:
            ModuleResult: Результат выполнения
        """
        if config is None:
            config = self.config

        if not self.validate_config(config):
            return ModuleResult(
                module_id=self.metadata.id,
                status="error",
                started_at=datetime.now(),
                completed_at=datetime.now(),
                execution_time_ms=0,
                error="Invalid module configuration"
            )

        start_time = datetime.now()
        timeout_seconds = config.timeout_seconds

        try:
            logger.info(
                f"Module '{self.metadata.id}' starting analysis "
                f"(timeout: {timeout_seconds}s)"
            )

            # Выполняем с таймаутом через ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_with_timeout, config)

                try:
                    # Ждем результат с таймаутом
                    results = future.result(timeout=timeout_seconds)

                    end_time = datetime.now()
                    execution_time = int((end_time - start_time).total_seconds() * 1000)

                    logger.info(
                        f"Module '{self.metadata.id}' completed. "
                        f"Time: {execution_time}ms"
                    )

                    return ModuleResult(
                        module_id=self.metadata.id,
                        status="success",
                        started_at=start_time,
                        completed_at=end_time,
                        execution_time_ms=execution_time,
                        data=results['formatted_data'],
                        charts=results['charts'],
                        recommendations=results['recommendations'],
                        alerts=results['alerts']
                    )

                except FuturesTimeoutError:
                    # Таймаут превышен
                    end_time = datetime.now()
                    execution_time = int((end_time - start_time).total_seconds() * 1000)

                    error_msg = (
                        f"Module execution exceeded timeout of {timeout_seconds}s"
                    )
                    logger.error(
                        f"Module '{self.metadata.id}' timed out after {timeout_seconds}s"
                    )

                    return ModuleResult(
                        module_id=self.metadata.id,
                        status="timeout",
                        started_at=start_time,
                        completed_at=end_time,
                        execution_time_ms=execution_time,
                        error=error_msg
                    )

        except Exception as e:
            end_time = datetime.now()
            execution_time = int((end_time - start_time).total_seconds() * 1000)

            logger.error(f"Module '{self.metadata.id}' failed: {e}", exc_info=True)

            return ModuleResult(
                module_id=self.metadata.id,
                status="error",
                started_at=start_time,
                completed_at=end_time,
                execution_time_ms=execution_time,
                error=str(e)
            )
