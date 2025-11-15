"""
Модули аналитики Binom Assistant
"""
from .base_module import BaseModule, ModuleMetadata, ModuleConfig, ModuleResult
from .registry import ModuleRegistry
from .module_runner import ModuleRunner

__all__ = [
    'BaseModule',
    'ModuleMetadata',
    'ModuleConfig',
    'ModuleResult',
    'ModuleRegistry',
    'ModuleRunner',
]
