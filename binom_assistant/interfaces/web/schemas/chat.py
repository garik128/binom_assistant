"""
Pydantic схемы для Chat API.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """Схема для одного сообщения в чате"""
    role: str = Field(..., description="Роль отправителя: 'user' или 'assistant'")
    content: str = Field(..., description="Текст сообщения")


class ChatRequest(BaseModel):
    """Схема запроса для отправки сообщения"""
    message: str = Field(..., description="Сообщение пользователя")
    chat_history: Optional[List[ChatMessage]] = Field(
        default=[],
        description="История предыдущих сообщений"
    )
    model: Optional[str] = Field(
        default=None,
        description="Модель для использования (если не указана - используется дефолтная)"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Максимальное количество токенов"
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Температура генерации (0.0-2.0)"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Системный промпт (опционально)"
    )
    context_limit: Optional[int] = Field(
        default=10,
        description="Количество сообщений истории для передачи в контексте"
    )
    use_modules: Optional[bool] = Field(
        default=False,
        description="Использовать AI агента с модулями аналитики"
    )
    modules_category: Optional[str] = Field(
        default="critical_alerts",
        description="Категория модулей для агента (если use_modules=True)"
    )


class TokenUsage(BaseModel):
    """Информация об использовании токенов"""
    prompt_tokens: int = Field(..., description="Токены в промпте")
    completion_tokens: int = Field(..., description="Токены в ответе")
    total_tokens: int = Field(..., description="Всего токенов")


class ChatResponse(BaseModel):
    """Схема ответа от AI"""
    response: str = Field(..., description="Ответ AI")
    model: str = Field(..., description="Использованная модель")
    usage: TokenUsage = Field(..., description="Информация об использовании токенов")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Временная метка ответа"
    )


class ModelInfo(BaseModel):
    """Информация о модели"""
    id: str = Field(..., description="ID модели")
    name: str = Field(..., description="Название модели")
    description: str = Field(default="", description="Описание модели")
    context_length: int = Field(default=0, description="Максимальная длина контекста")
    pricing: Dict[str, Any] = Field(default_factory=dict, description="Информация о ценах")


class ModelsListResponse(BaseModel):
    """Схема ответа со списком моделей"""
    models: List[ModelInfo] = Field(..., description="Список доступных моделей")


class TemplateCreate(BaseModel):
    """Схема для создания шаблона"""
    title: str = Field(..., min_length=1, max_length=255, description="Название шаблона")
    prompt: str = Field(..., min_length=1, description="Текст промпта")
    icon: str = Field(default="message", max_length=50, description="Иконка шаблона")


class TemplateUpdate(BaseModel):
    """Схема для обновления шаблона"""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Название шаблона")
    prompt: Optional[str] = Field(None, min_length=1, description="Текст промпта")
    icon: Optional[str] = Field(None, max_length=50, description="Иконка шаблона")


class TemplateResponse(BaseModel):
    """Схема ответа с информацией о шаблоне"""
    id: int
    title: str
    prompt: str
    icon: str
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    """Схема ответа со списком шаблонов"""
    templates: List[TemplateResponse] = Field(..., description="Список шаблонов")
