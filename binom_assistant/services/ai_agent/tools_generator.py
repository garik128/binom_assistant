"""
Генератор OpenAI tools для модулей аналитики
"""
import json
import os
from typing import List, Dict, Any


# Определение DB tools (прямой доступ к БД)
DB_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_campaigns_list",
            "description": "Получить список кампаний из БД с фильтрацией. Используй когда нужны базовые данные о кампаниях (названия, группы, статус).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество записей (по умолчанию 100, макс 500)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Фильтр по активности (true=активные, false=неактивные, не указывать=все)"
                    },
                    "is_cpl_mode": {
                        "type": "boolean",
                        "description": "Фильтр по типу оплаты (true=CPL, false=CPA, не указывать=все)"
                    },
                    "group_name": {
                        "type": "string",
                        "description": "Фильтр по группе (точное совпадение)"
                    },
                    "search_name": {
                        "type": "string",
                        "description": "Поиск по имени кампании (частичное совпадение)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaign_daily_stats",
            "description": "Получить дневную статистику конкретной кампании. Используй для детального анализа динамики по дням.",
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_id": {
                        "type": "integer",
                        "description": "Внутренний ID кампании (internal_id из get_campaigns_list)"
                    },
                    "binom_id": {
                        "type": "integer",
                        "description": "ID кампании в Binom (альтернатива campaign_id)"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Дата начала в формате YYYY-MM-DD"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата окончания в формате YYYY-MM-DD"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество дней (по умолчанию 100)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "min_cost": {
                        "type": "number",
                        "description": "Минимальный расход для фильтрации шума (рекомендуется 1.0)"
                    },
                    "min_clicks": {
                        "type": "integer",
                        "description": "Минимальное количество кликов для фильтрации шума (рекомендуется 50)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_campaigns_stats_aggregated",
            "description": "Получить агрегированную статистику по всем кампаниям за период. Используй для сравнения кампаний, поиска лучших/худших.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Дата начала в формате YYYY-MM-DD (по умолчанию -7 дней)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата окончания в формате YYYY-MM-DD (по умолчанию сегодня)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество кампаний (по умолчанию 100)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "min_cost": {
                        "type": "number",
                        "description": "Минимальный расход за период для фильтрации шума"
                    },
                    "is_cpl_mode": {
                        "type": "boolean",
                        "description": "Фильтр по типу оплаты (true=CPL, false=CPA)"
                    },
                    "group_name": {
                        "type": "string",
                        "description": "Фильтр по группе кампаний"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_traffic_sources_stats",
            "description": "Получить агрегированную статистику по источникам трафика за период. Используй для анализа качества источников.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Дата начала в формате YYYY-MM-DD (по умолчанию -7 дней)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата окончания в формате YYYY-MM-DD (по умолчанию сегодня)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество источников (по умолчанию 100)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "min_cost": {
                        "type": "number",
                        "description": "Минимальный расход за период"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_affiliate_networks_stats",
            "description": "Получить агрегированную статистику по партнерским сетям за период. Используй для анализа качества партнерок и approve rate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Дата начала в формате YYYY-MM-DD (по умолчанию -7 дней)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата окончания в формате YYYY-MM-DD (по умолчанию сегодня)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество партнерок (по умолчанию 100)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "min_revenue": {
                        "type": "number",
                        "description": "Минимальный доход за период"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_offers_stats",
            "description": "Получить агрегированную статистику по офферам за период. Используй для анализа прибыльности офферов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Дата начала в формате YYYY-MM-DD (по умолчанию -7 дней)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Дата окончания в формате YYYY-MM-DD (по умолчанию сегодня)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество офферов (по умолчанию 100)",
                        "minimum": 1,
                        "maximum": 500
                    },
                    "min_revenue": {
                        "type": "number",
                        "description": "Минимальный доход за период"
                    },
                    "network_id": {
                        "type": "integer",
                        "description": "Фильтр по ID партнерской сети"
                    }
                },
                "required": []
            }
        }
    }
]


class ToolsGenerator:
    """
    Генератор OpenAI function tools для модулей.

    Преобразует метаданные модулей в формат OpenAI function calling.
    """

    def __init__(self):
        """Инициализация генератора с загрузкой метаданных"""
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """
        Загружает метаданные модулей из JSON файла.

        Returns:
            Dict с метаданными всех модулей
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        metadata_path = os.path.join(current_dir, 'modules_metadata.json')

        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def generate_tool_for_module(self, category: str, module_id: str) -> Dict[str, Any]:
        """
        Генерирует OpenAI tool для конкретного модуля.

        Args:
            category: Категория модуля (например, "critical_alerts")
            module_id: ID модуля (например, "bleeding_detector")

        Returns:
            Dict в формате OpenAI function tool
        """
        if category not in self.metadata:
            raise ValueError(f"Category '{category}' not found in metadata")

        if module_id not in self.metadata[category]:
            raise ValueError(f"Module '{module_id}' not found in category '{category}'")

        module_meta = self.metadata[category][module_id]

        # Преобразуем параметры модуля в OpenAI format
        properties = {}
        for param_name, param_meta in module_meta['params'].items():
            prop = {
                "type": param_meta['type'],
                "description": param_meta['description']
            }

            # Добавляем ограничения для числовых параметров
            if param_meta['type'] in ['number', 'integer']:
                if 'min' in param_meta:
                    prop['minimum'] = param_meta['min']
                if 'max' in param_meta:
                    prop['maximum'] = param_meta['max']

            properties[param_name] = prop

        return {
            "type": "function",
            "function": {
                "name": f"run_{module_id}",
                "description": f"{module_meta['name']}. {module_meta['description']}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": []  # Все параметры опциональные, есть дефолты
                }
            }
        }

    def generate_tools_for_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Генерирует OpenAI tools для всех модулей категории.
        ВАЖНО: Теперь включает DB tools для всех категорий!

        Args:
            category: Категория модулей (например, "critical_alerts" или "universal")

        Returns:
            List of OpenAI function tools
        """
        # Специальный случай: "universal" - возвращаем ВСЕ модули из всех категорий
        if category == "universal":
            return self.generate_all_tools()

        if category not in self.metadata:
            raise ValueError(f"Category '{category}' not found in metadata")

        tools = []

        # Добавляем модули категории
        for module_id in self.metadata[category].keys():
            tool = self.generate_tool_for_module(category, module_id)
            tools.append(tool)

        # ВАЖНО: Добавляем DB tools для всех категорий
        tools.extend(DB_TOOLS_DEFINITIONS)

        return tools

    def generate_all_tools(self) -> List[Dict[str, Any]]:
        """
        Генерирует OpenAI tools для всех модулей всех категорий + DB tools.

        Returns:
            List of OpenAI function tools
        """
        tools = []

        # Добавляем tools из всех категорий (без дублирования DB tools через рекурсию)
        for category in self.metadata.keys():
            for module_id in self.metadata[category].keys():
                tool = self.generate_tool_for_module(category, module_id)
                tools.append(tool)

        # Добавляем DB tools один раз
        tools.extend(DB_TOOLS_DEFINITIONS)

        return tools

    def get_module_info(self, module_id: str) -> tuple[str, Dict[str, Any]]:
        """
        Получает информацию о модуле по его ID.

        Args:
            module_id: ID модуля

        Returns:
            (category, module_metadata)

        Raises:
            ValueError: Если модуль не найден
        """
        for category, modules in self.metadata.items():
            if module_id in modules:
                return category, modules[module_id]

        raise ValueError(f"Module '{module_id}' not found in any category")
