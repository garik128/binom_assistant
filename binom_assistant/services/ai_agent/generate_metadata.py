"""
Скрипт для генерации modules_metadata.json из зарегистрированных модулей
"""
import json
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from modules.registry import get_registry
from modules.startup import register_all_modules

def generate_metadata_json():
    """Генерирует modules_metadata.json из зарегистрированных модулей"""

    # Регистрируем все модули
    register_all_modules()
    registry = get_registry()

    # Получаем список всех модулей
    modules = registry.list_modules()

    # Группируем по категориям
    metadata = {}

    for module_meta in modules:
        category = module_meta.category
        module_id = module_meta.id

        if category not in metadata:
            metadata[category] = {}

        # Получаем экземпляр модуля для доступа к параметрам
        module_instance = registry.get_module_instance(module_id)
        if not module_instance:
            print(f"Warning: Could not get instance for module {module_id}")
            continue

        # Получаем параметры модуля
        param_metadata = module_instance.get_param_metadata()

        # Формируем структуру для JSON
        params_json = {}
        for param_name, param_info in param_metadata.items():
            params_json[param_name] = {
                "type": param_info.get("type", "number"),
                "default": param_info.get("default"),
                "min": param_info.get("min"),
                "max": param_info.get("max"),
                "description": param_info.get("description", "")
            }

            # Удаляем None значения
            params_json[param_name] = {k: v for k, v in params_json[param_name].items() if v is not None}

        metadata[category][module_id] = {
            "name": module_meta.name,
            "description": module_meta.description,
            "params": params_json
        }

    # Сохраняем в JSON
    output_path = os.path.join(os.path.dirname(__file__), 'modules_metadata.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"✓ Generated metadata for {len(modules)} modules in {len(metadata)} categories")
    print(f"✓ Saved to: {output_path}")

    # Выводим статистику
    for category, mods in metadata.items():
        print(f"  - {category}: {len(mods)} modules")

if __name__ == "__main__":
    generate_metadata_json()
