"""
AI Agent для анализа модулей аналитики
"""
import httpx
import json
import logging
from typing import List, Dict, Any, Optional
from config.config import get_config
from .tools_generator import ToolsGenerator
from .prompt_manager import get_prompt_manager

# Импорт DB tools для прямого доступа к БД
from . import db_tools

logger = logging.getLogger(__name__)


class AIAgentService:
    """
    Сервис для работы с AI агентом, который анализирует модули.

    Использует OpenRouter API для вызова GPT-4o-mini с function calling.
    """

    def __init__(self):
        """Инициализация сервиса"""
        self.config = get_config()

        # Получаем конфигурацию OpenRouter (маппинг в config.py)
        openrouter_config = self.config.get_section("openrouter")

        self.api_key = openrouter_config.get("api_key")
        self.api_base = "https://openrouter.ai/api/v1"
        self.model = openrouter_config.get("model", "openai/gpt-4.1-mini")
        self.max_tokens = openrouter_config.get("max_tokens", 16000)  # Дефолт 16k для работы с большими данными
        self.tools_generator = ToolsGenerator()

        # URL для вызова модулей (локальный API)
        self.modules_api_base = "http://localhost:8000/api/v1/modules"

    async def call_module(self, module_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Вызывает модуль аналитики через API.

        Args:
            module_id: ID модуля
            params: Параметры запуска (опционально)

        Returns:
            Dict с результатами модуля
        """
        url = f"{self.modules_api_base}/{module_id}/run"
        payload = {
            "use_cache": False,  # Всегда свежие данные для агента
            "params": params or {}
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=60.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error calling module {module_id}: {e}")
            raise

    async def call_openrouter(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Вызывает OpenRouter API.

        Args:
            messages: История сообщений
            tools: Список доступных tools
            model: Модель для использования (если None - используется дефолтная)

        Returns:
            Ответ от API
        """
        use_model = model or self.model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": use_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",  # AI сам решает когда вызывать tools
            "max_tokens": self.max_tokens  # ВАЖНО: лимит токенов для обработки больших данных от DB tools
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Agent calling OpenRouter: model={use_model}, messages={len(messages)}, tools={len(tools)}")
                response = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                logger.debug(f"OpenRouter response received successfully")
                return result
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error calling OpenRouter: {e}", exc_info=True)
            raise

    async def analyze(
        self,
        user_query: str,
        category: str = "critical_alerts",
        chat_history: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None
    ) -> str:
        """
        Анализирует запрос пользователя с помощью AI агента.

        Args:
            user_query: Запрос пользователя
            category: Категория модулей для использования
            chat_history: История предыдущих сообщений (опционально)
            model: Модель для использования (если None - используется дефолтная)

        Returns:
            Markdown ответ от агента
        """
        # Используем переданную модель или дефолтную
        use_model = model or self.model

        # Получаем специализированный промпт для категории (кастомный или дефолтный)
        prompt_manager = get_prompt_manager()
        system_prompt = prompt_manager.get_prompt(category)

        # Добавляем текущую дату/время в промпт для контекста
        from datetime import datetime
        import locale

        # Получаем текущую дату/время с учетом timezone конфига
        current_datetime = datetime.now()

        # Пытаемся получить название дня недели на русском
        try:
            locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
            day_name = current_datetime.strftime('%A')
        except:
            # Если локаль недоступна - словарь дней недели
            weekdays_ru = {
                'Monday': 'Понедельник',
                'Tuesday': 'Вторник',
                'Wednesday': 'Среда',
                'Thursday': 'Четверг',
                'Friday': 'Пятница',
                'Saturday': 'Суббота',
                'Sunday': 'Воскресенье'
            }
            day_name_en = current_datetime.strftime('%A')
            day_name = weekdays_ru.get(day_name_en, day_name_en)

        system_prompt_with_context = f"""{system_prompt}

---

## Текущий контекст:

**Сегодня:** {current_datetime.strftime('%Y-%m-%d')} ({day_name})
**Время:** {current_datetime.strftime('%H:%M')}

Используй эту информацию для интерпретации временных запросов пользователя ("вчера", "за последние 3 дня", "на этой неделе" и т.д.).
"""

        # Генерируем tools для категории
        tools = self.tools_generator.generate_tools_for_category(category)

        # Начальные сообщения
        messages = [
            {"role": "system", "content": system_prompt_with_context}
        ]

        # Добавляем историю если есть
        if chat_history:
            messages.extend(chat_history)

        # Добавляем текущий запрос пользователя
        messages.append({"role": "user", "content": user_query})

        max_iterations = 10  # Защита от бесконечного цикла
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Вызываем OpenRouter
            try:
                response = await self.call_openrouter(messages, tools, use_model)

                # Проверяем структуру ответа
                if 'choices' not in response or not response['choices']:
                    logger.error(f"Invalid OpenRouter response: {response}")
                    return "⚠️ Получен некорректный ответ от AI. Попробуйте еще раз."

                # Получаем ответ
                message = response['choices'][0]['message']

            except Exception as e:
                logger.error(f"Error in analyze iteration {iteration}: {e}", exc_info=True)
                return f"⚠️ Ошибка при обращении к AI: {str(e)}"

            # Если нет tool_calls, значит агент завершил работу
            if not message.get('tool_calls'):
                # Возвращаем финальный ответ
                final_response = message.get('content', 'Нет ответа от агента')
                logger.info(f"Agent final response length: {len(final_response)}, first 200 chars: {final_response[:200]}")
                return final_response

            # Агент хочет вызвать tools
            messages.append(message)

            # Обрабатываем каждый tool call
            for tool_call in message['tool_calls']:
                function_name = tool_call['function']['name']
                function_args = json.loads(tool_call['function']['arguments'])

                logger.info(f"Agent calling: {function_name} with args: {function_args}")

                try:
                    # Проверяем: это DB tool или модуль?
                    if self._is_db_tool(function_name):
                        # Вызываем DB tool
                        result = self._call_db_tool(function_name, function_args)
                    else:
                        # Извлекаем module_id из имени функции (формат: run_{module_id})
                        module_id = function_name.replace('run_', '')
                        # Вызываем модуль
                        result = await self.call_module(module_id, function_args)

                    # Добавляем результат в историю
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "name": function_name,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
                except Exception as e:
                    # Если ошибка - сообщаем агенту
                    error_msg = f"Ошибка при вызове: {str(e)}"
                    logger.error(error_msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "name": function_name,
                        "content": json.dumps({"error": error_msg}, ensure_ascii=False)
                    })

        # Если превысили лимит итераций
        return "⚠️ Превышен лимит итераций анализа. Попробуйте упростить запрос."

    def _is_db_tool(self, function_name: str) -> bool:
        """
        Проверяет, является ли функция DB tool.

        Args:
            function_name: Имя функции

        Returns:
            bool: True если это DB tool
        """
        db_tool_names = [
            'get_campaigns_list',
            'get_campaign_daily_stats',
            'get_campaigns_stats_aggregated',
            'get_traffic_sources_stats',
            'get_affiliate_networks_stats',
            'get_offers_stats'
        ]
        return function_name in db_tool_names

    def _call_db_tool(self, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Вызывает DB tool (синхронно).

        Args:
            function_name: Имя DB tool функции
            args: Аргументы функции

        Returns:
            Dict с результатами

        Raises:
            ValueError: Если DB tool не найден
        """
        # Получаем функцию из модуля db_tools
        if not hasattr(db_tools, function_name):
            raise ValueError(f"DB tool '{function_name}' not found")

        tool_function = getattr(db_tools, function_name)

        logger.info(f"Calling DB tool: {function_name} with args: {args}")

        # Вызываем функцию с аргументами
        result = tool_function(**args)

        logger.info(f"DB tool {function_name} returned: {len(str(result))} chars")

        return result


# Глобальный экземпляр сервиса
_agent_service: Optional[AIAgentService] = None


def get_agent_service() -> AIAgentService:
    """Получает глобальный экземпляр сервиса"""
    global _agent_service
    if _agent_service is None:
        _agent_service = AIAgentService()
    return _agent_service
