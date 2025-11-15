"""
Менеджер для работы с системными промптами агентов.
Поддерживает кастомизацию и сброс к дефолтным значениям.
"""
import json
import os
from typing import Optional, Dict
from .category_prompts import CATEGORY_PROMPTS


class PromptManager:
    """
    Управление системными промптами агентов.

    Хранит кастомные промпты в JSON файле,
    позволяет получать и редактировать промпты,
    возвращаться к дефолтным значениям.
    """

    def __init__(self):
        """Инициализация менеджера промптов"""
        self.custom_prompts_file = self._get_custom_prompts_path()
        self._ensure_file_exists()

    def _get_custom_prompts_path(self) -> str:
        """Получить путь к файлу с кастомными промптами"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'custom_prompts.json')

    def _ensure_file_exists(self):
        """Создать файл с кастомными промптами если не существует"""
        if not os.path.exists(self.custom_prompts_file):
            with open(self.custom_prompts_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _load_custom_prompts(self) -> Dict[str, str]:
        """
        Загрузить кастомные промпты из файла.

        Returns:
            Dict[category_id, custom_prompt]
        """
        try:
            with open(self.custom_prompts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_custom_prompts(self, prompts: Dict[str, str]):
        """
        Сохранить кастомные промпты в файл.

        Args:
            prompts: Dict[category_id, custom_prompt]
        """
        with open(self.custom_prompts_file, 'w', encoding='utf-8') as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)

    def get_prompt(self, category_id: str) -> str:
        """
        Получить промпт для категории (кастомный или дефолтный).

        Args:
            category_id: ID категории агента

        Returns:
            Системный промпт

        Raises:
            ValueError: Если категория не существует
        """
        if category_id not in CATEGORY_PROMPTS:
            raise ValueError(f"Unknown category: {category_id}")

        # Сначала проверяем кастомные промпты
        custom_prompts = self._load_custom_prompts()
        if category_id in custom_prompts:
            return custom_prompts[category_id]

        # Если нет кастомного - возвращаем дефолтный
        return CATEGORY_PROMPTS[category_id]

    def get_default_prompt(self, category_id: str) -> str:
        """
        Получить дефолтный промпт для категории.

        Args:
            category_id: ID категории агента

        Returns:
            Дефолтный системный промпт

        Raises:
            ValueError: Если категория не существует
        """
        if category_id not in CATEGORY_PROMPTS:
            raise ValueError(f"Unknown category: {category_id}")

        return CATEGORY_PROMPTS[category_id]

    def update_prompt(self, category_id: str, new_prompt: str):
        """
        Обновить промпт для категории.

        Args:
            category_id: ID категории агента
            new_prompt: Новый текст промпта

        Raises:
            ValueError: Если категория не существует
        """
        if category_id not in CATEGORY_PROMPTS:
            raise ValueError(f"Unknown category: {category_id}")

        custom_prompts = self._load_custom_prompts()
        custom_prompts[category_id] = new_prompt
        self._save_custom_prompts(custom_prompts)

    def reset_to_default(self, category_id: str):
        """
        Сбросить промпт к дефолтному значению.

        Args:
            category_id: ID категории агента

        Raises:
            ValueError: Если категория не существует
        """
        if category_id not in CATEGORY_PROMPTS:
            raise ValueError(f"Unknown category: {category_id}")

        custom_prompts = self._load_custom_prompts()
        if category_id in custom_prompts:
            del custom_prompts[category_id]
            self._save_custom_prompts(custom_prompts)

    def is_custom(self, category_id: str) -> bool:
        """
        Проверить, используется ли кастомный промпт для категории.

        Args:
            category_id: ID категории агента

        Returns:
            True если используется кастомный промпт
        """
        custom_prompts = self._load_custom_prompts()
        return category_id in custom_prompts

    def get_all_categories(self) -> Dict[str, Dict[str, any]]:
        """
        Получить информацию о всех категориях и их промптах.

        Returns:
            Dict с информацией: {category_id: {is_custom, has_default}}
        """
        custom_prompts = self._load_custom_prompts()
        result = {}

        for category_id in CATEGORY_PROMPTS.keys():
            result[category_id] = {
                "is_custom": category_id in custom_prompts,
                "has_default": True
            }

        return result


# Singleton instance
_prompt_manager = None


def get_prompt_manager() -> PromptManager:
    """
    Получить singleton instance менеджера промптов.

    Returns:
        PromptManager instance
    """
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
