"""
Сервис для работы с OpenRouter AI API.
"""
import httpx
import logging
from typing import List, Dict, Optional, Any
from config import get_config

logger = logging.getLogger(__name__)


class AIService:
    """
    Сервис для генерации AI ответов через OpenRouter API.
    """

    def __init__(self):
        """Инициализация сервиса"""
        self.config = get_config()
        openrouter_config = self.config.get_section("openrouter")

        self.api_key = openrouter_config.get("api_key")
        self.model = openrouter_config.get("model", "openai/gpt-4.1-mini")
        self.max_tokens = openrouter_config.get("max_tokens", 8000)
        self.base_url = "https://openrouter.ai/api/v1"

        if not self.api_key:
            logger.warning("OpenRouter API key not configured")

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Генерация ответа от AI.

        Args:
            messages: История сообщений в формате [{"role": "user/assistant", "content": "..."}]
            model: Модель для использования (если None - использует дефолтную из конфига)
            max_tokens: Максимальное количество токенов (если None - использует из конфига)
            temperature: Температура генерации (0.0-1.0)
            system_prompt: Системный промпт (опционально)

        Returns:
            Dict с полями:
                - response: текст ответа
                - model: использованная модель
                - usage: информация о токенах
                - cost: стоимость запроса (если доступна)
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured")

        # Используем переданные параметры или значения по умолчанию
        use_model = model or self.model
        use_max_tokens = max_tokens or self.max_tokens

        # Формируем список сообщений
        api_messages = []

        # Добавляем системный промпт если указан
        if system_prompt:
            api_messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Добавляем историю сообщений
        api_messages.extend(messages)

        # Логируем запрос
        logger.info(f"Sending request to OpenRouter: model={use_model}, messages={len(api_messages)}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Binom Assistant"
                    },
                    json={
                        "model": use_model,
                        "messages": api_messages,
                        "max_tokens": use_max_tokens,
                        "temperature": temperature
                    }
                )

                response.raise_for_status()
                data = response.json()

                # Извлекаем ответ
                ai_response = data["choices"][0]["message"]["content"]

                # Извлекаем информацию об использовании токенов
                usage = data.get("usage", {})

                # Формируем результат
                result = {
                    "response": ai_response,
                    "model": data.get("model", use_model),
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0)
                    }
                }

                logger.info(
                    f"Response received: tokens={result['usage']['total_tokens']}, "
                    f"model={result['model']}"
                )

                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API HTTP error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"OpenRouter API error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"OpenRouter API request error: {e}")
            raise Exception(f"Failed to connect to OpenRouter API: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in AI service: {e}")
            raise

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Получение списка доступных моделей из OpenRouter.

        Returns:
            Список моделей с информацией о них
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                    }
                )

                response.raise_for_status()
                data = response.json()

                # Фильтруем и форматируем модели
                models = []
                for model in data.get("data", []):
                    models.append({
                        "id": model.get("id"),
                        "name": model.get("name", model.get("id")),
                        "description": model.get("description", ""),
                        "pricing": model.get("pricing", {}),
                        "context_length": model.get("context_length", 0)
                    })

                return models

        except Exception as e:
            logger.error(f"Failed to fetch models from OpenRouter: {e}")
            # Возвращаем базовый список популярных моделей
            return self._get_default_models()

    def _get_default_models(self) -> List[Dict[str, Any]]:
        """
        Возвращает список популярных моделей по умолчанию.
        """
        return [
            {
                "id": "openai/gpt-4.1-mini",
                "name": "GPT-4.1 Mini",
                "description": "Fast and affordable model (default)",
                "pricing": {},
                "context_length": 128000
            },
            {
                "id": "openai/gpt-4o-mini",
                "name": "GPT-4o Mini",
                "description": "Fast and affordable model",
                "pricing": {},
                "context_length": 128000
            },
            {
                "id": "openai/gpt-4-turbo",
                "name": "GPT-4 Turbo",
                "description": "Most capable GPT-4 model",
                "pricing": {},
                "context_length": 128000
            },
            {
                "id": "openai/gpt-3.5-turbo",
                "name": "GPT-3.5 Turbo",
                "description": "Fast and cost-effective",
                "pricing": {},
                "context_length": 16385
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "description": "Most intelligent Claude model",
                "pricing": {},
                "context_length": 200000
            },
            {
                "id": "anthropic/claude-3-opus",
                "name": "Claude 3 Opus",
                "description": "Powerful Claude model",
                "pricing": {},
                "context_length": 200000
            },
            {
                "id": "anthropic/claude-3-sonnet",
                "name": "Claude 3 Sonnet",
                "description": "Balanced Claude model",
                "pricing": {},
                "context_length": 200000
            },
            {
                "id": "google/gemini-pro-1.5",
                "name": "Gemini Pro 1.5",
                "description": "Google's advanced model",
                "pricing": {},
                "context_length": 1000000
            }
        ]


# Синглтон для AI сервиса
_ai_service_instance: Optional[AIService] = None


def get_ai_service() -> AIService:
    """
    Получение синглтона AI сервиса.

    Returns:
        Экземпляр AIService
    """
    global _ai_service_instance

    if _ai_service_instance is None:
        _ai_service_instance = AIService()
        logger.info("AI Service initialized")

    return _ai_service_instance
