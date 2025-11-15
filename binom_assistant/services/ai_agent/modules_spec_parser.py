"""
Парсер спецификации модулей из modules_full_specification.md
"""
import os
import re
from typing import Dict, List, Any


class ModulesSpecParser:
    """Парсер для получения детальной информации о модулях"""

    def __init__(self):
        """Инициализация парсера"""
        # Путь к файлу спецификации
        spec_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            'modules',
            'modules_full_specification.md'
        )

        self.spec_data = self._parse_specification(spec_path)

    def _parse_specification(self, file_path: str) -> Dict[str, Any]:
        """
        Парсит markdown файл со спецификацией модулей

        Returns:
            Dict с информацией о модулях {slug: {данные}}
        """
        modules = {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Разбиваем на блоки модулей (разделенные ---)
            # Паттерн для поиска модулей
            module_pattern = r'\*\*Slug:\*\*\s*`([^`]+)`\s*\n\*\*Категория:\*\*\s*([^\n]+)\s*\n\*\*Краткое описание:\*\*\s*([^\n]+)\s*\n\*\*Детальное описание:\*\*\s*([^\n]+)'

            for match in re.finditer(module_pattern, content):
                slug = match.group(1).strip()
                category = match.group(2).strip()
                short_desc = match.group(3).strip()
                detailed_desc = match.group(4).strip()

                # Получаем блок текста после этого модуля до следующего "---" или следующего **Slug:**
                start_pos = match.end()
                next_module = re.search(r'\*\*Slug:\*\*', content[start_pos:])
                separator = re.search(r'---', content[start_pos:])

                if next_module and separator:
                    end_pos = start_pos + min(next_module.start(), separator.start())
                elif next_module:
                    end_pos = start_pos + next_module.start()
                elif separator:
                    end_pos = start_pos + separator.start()
                else:
                    end_pos = len(content)

                logic_text = content[start_pos:end_pos].strip()

                # Извлекаем секцию "Логика"
                logic_match = re.search(r'\*\*Логика[^:]*:\*\*\s*((?:- .+\n?)+)', logic_text)
                logic_points = []
                if logic_match:
                    logic_lines = logic_match.group(1).strip().split('\n')
                    logic_points = [line.strip('- ').strip() for line in logic_lines if line.strip().startswith('-')]

                modules[slug] = {
                    'slug': slug,
                    'category': category,
                    'short_description': short_desc,
                    'detailed_description': detailed_desc,
                    'logic': logic_points
                }

        except FileNotFoundError:
            print(f"Warning: modules_full_specification.md not found at {file_path}")
        except Exception as e:
            print(f"Error parsing modules specification: {e}")

        return modules

    def get_module_info(self, slug: str) -> Dict[str, Any]:
        """
        Получает информацию о конкретном модуле

        Args:
            slug: ID модуля

        Returns:
            Dict с информацией о модуле
        """
        return self.spec_data.get(slug, {})

    def get_modules_by_category(self, category_name: str) -> List[Dict[str, Any]]:
        """
        Получает все модули определенной категории

        Args:
            category_name: Название категории (например, "Критические алерты")

        Returns:
            List модулей этой категории
        """
        return [
            module for module in self.spec_data.values()
            if module.get('category', '').lower() == category_name.lower()
        ]

    def get_all_modules(self) -> Dict[str, Any]:
        """
        Возвращает информацию о всех модулях

        Returns:
            Dict со всеми модулями
        """
        return self.spec_data


# Глобальный экземпляр парсера
_parser = None


def get_spec_parser() -> ModulesSpecParser:
    """Получает глобальный экземпляр парсера"""
    global _parser
    if _parser is None:
        _parser = ModulesSpecParser()
    return _parser
