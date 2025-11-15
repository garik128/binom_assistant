"""
Реестр модулей аналитики
"""
import logging
import threading
from typing import Dict, List, Optional, Type
from .base_module import BaseModule, ModuleMetadata

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Реестр всех доступных модулей аналитики.

    Хранит информацию о модулях и позволяет их находить по ID или категории.
    """

    def __init__(self):
        self._modules: Dict[str, Type[BaseModule]] = {}
        self._metadata_cache: Dict[str, ModuleMetadata] = {}
        logger.info("ModuleRegistry initialized")

    def register(self, module_class: Type[BaseModule]) -> None:
        """
        Регистрирует модуль в реестре и кэширует metadata.

        Args:
            module_class: Класс модуля (наследник BaseModule)

        Raises:
            ValueError: Если модуль с таким ID уже зарегистрирован
        """
        # Создаем временный экземпляр для получения метаданных ОДИН раз
        instance = module_class()
        module_id = instance.metadata.id
        metadata = instance.metadata

        if module_id in self._modules:
            logger.warning(f"Module '{module_id}' already registered, overwriting")

        self._modules[module_id] = module_class
        self._metadata_cache[module_id] = metadata  # Кэшируем metadata
        logger.info(f"Module '{module_id}' registered")

    def unregister(self, module_id: str) -> None:
        """
        Удаляет модуль из реестра.

        Args:
            module_id: ID модуля
        """
        if module_id in self._modules:
            del self._modules[module_id]
            # Удаляем и из кэша metadata
            if module_id in self._metadata_cache:
                del self._metadata_cache[module_id]
            logger.info(f"Module '{module_id}' unregistered")
        else:
            logger.warning(f"Module '{module_id}' not found in registry")

    def get_module(self, module_id: str) -> Optional[Type[BaseModule]]:
        """
        Получает класс модуля по ID.

        Args:
            module_id: ID модуля

        Returns:
            Type[BaseModule]: Класс модуля или None если не найден
        """
        return self._modules.get(module_id)

    def get_module_instance(self, module_id: str) -> Optional[BaseModule]:
        """
        Создает экземпляр модуля по ID.

        Args:
            module_id: ID модуля

        Returns:
            BaseModule: Экземпляр модуля или None если не найден
        """
        module_class = self.get_module(module_id)
        if module_class:
            return module_class()
        return None

    def list_modules(self) -> List[ModuleMetadata]:
        """
        Возвращает список метаданных всех зарегистрированных модулей.
        Использует кэш для избежания создания экземпляров.

        Returns:
            List[ModuleMetadata]: Список метаданных
        """
        return list(self._metadata_cache.values())

    def list_by_category(self, category: str) -> List[ModuleMetadata]:
        """
        Возвращает список модулей определенной категории.
        Использует кэш для избежания создания экземпляров.

        Args:
            category: Категория модулей

        Returns:
            List[ModuleMetadata]: Список метаданных модулей категории
        """
        return [
            metadata for metadata in self._metadata_cache.values()
            if metadata.category == category
        ]

    def list_categories(self) -> List[str]:
        """
        Возвращает список всех категорий.
        Использует кэш для избежания создания экземпляров.

        Returns:
            List[str]: Список уникальных категорий
        """
        categories = {
            metadata.category for metadata in self._metadata_cache.values()
        }
        return sorted(list(categories))

    def get_count(self) -> int:
        """
        Возвращает количество зарегистрированных модулей.

        Returns:
            int: Количество модулей
        """
        return len(self._modules)


# Глобальный экземпляр реестра
_global_registry: Optional[ModuleRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> ModuleRegistry:
    """
    Получает глобальный экземпляр реестра модулей.
    Потокобезопасно.

    Returns:
        ModuleRegistry: Глобальный реестр
    """
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            # Double-check locking pattern
            if _global_registry is None:
                _global_registry = ModuleRegistry()
    return _global_registry
