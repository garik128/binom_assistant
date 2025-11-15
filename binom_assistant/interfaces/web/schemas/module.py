"""
Pydantic схемы для модулей аналитики
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime


class ModuleMetadataResponse(BaseModel):
    """Метаданные модуля"""
    id: str
    name: str
    category: str
    description: str
    detailed_description: Optional[str] = None
    version: str
    author: str
    priority: str
    tags: List[str]
    enabled: bool = False
    status: str = "idle"
    last_run: Optional[datetime] = None
    last_result: Optional[Dict[str, Any]] = None


class ModuleConfigResponse(BaseModel):
    """Конфигурация модуля"""
    enabled: bool
    schedule: Optional[str]
    alerts_enabled: bool = False
    timeout_seconds: int
    cache_ttl_seconds: int
    params: Dict[str, Any]


class ModuleInfoResponse(BaseModel):
    """Полная информация о модуле"""
    model_config = {"exclude_none": False}

    metadata: ModuleMetadataResponse
    config: ModuleConfigResponse
    param_metadata: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    severity_metadata: Dict[str, Any] = Field(default_factory=dict)


class ModuleListResponse(BaseModel):
    """Список модулей"""
    modules: List[ModuleMetadataResponse]
    total: int
    categories: List[str]


class ModuleResultResponse(BaseModel):
    """Результат выполнения модуля"""
    module_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    execution_time_ms: int
    data: Dict[str, Any]
    charts: List[Dict[str, Any]]
    recommendations: List[str]
    alerts: List[Dict[str, Any]]
    error: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class ModuleRunHistoryItem(BaseModel):
    """Элемент истории запусков"""
    id: int
    module_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    execution_time_ms: Optional[int]
    error: Optional[str]
    summary: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class ModuleRunHistoryResponse(BaseModel):
    """История запусков модуля"""
    runs: List[ModuleRunHistoryItem]
    total: int


class ModuleConfigUpdate(BaseModel):
    """Обновление конфигурации модуля"""
    enabled: Optional[bool] = None
    schedule: Optional[str] = None
    alerts_enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    cache_ttl_seconds: Optional[int] = None
    params: Optional[Dict[str, Any]] = None


class ModuleRunRequest(BaseModel):
    """Запрос на запуск модуля"""
    use_cache: bool = Field(default=True, description="Использовать кэш")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Параметры запуска")
