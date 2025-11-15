"""
HTTP клиент для работы с Binom API
"""
import logging
import time
from typing import Dict, Any, Optional, List
import httpx

# Импорт конфига с учетом структуры проекта
import sys
from pathlib import Path

# Добавляем корневую папку binom_assistant в путь
root_dir = Path(__file__).parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from config import get_config


logger = logging.getLogger(__name__)


class BinomClient:
    """
    Клиент для работы с Binom API

    Использование:
        client = BinomClient()
        campaigns = client.get_campaigns(date="3")
    """

    def __init__(self):
        """Инициализация клиента"""
        config = get_config()

        # Валидация API ключа
        self.api_key = config.binom_api_key
        if not self.api_key:
            raise ValueError("Binom API key is required but not configured (BINOM_API_KEY)")

        # Нормализация base_url
        base_url = config.binom_url
        if not base_url:
            raise ValueError("Binom URL is required but not configured (BINOM_URL)")

        # Убираем trailing slash
        base_url = base_url.rstrip('/')

        # Если URL заканчивается на .php, это полный путь к API
        # Иначе это просто домен, и нужно будет добавить /index.php
        self.base_url = base_url
        self.has_api_path = base_url.endswith('.php')

        self.timeout = config.get('binom.timeout', 30)
        self.retry_attempts = config.get('binom.retry_attempts', 3)
        self.retry_delay = config.get('binom.retry_delay', 2)

        # Получаем timezone offset для API запросов
        self.timezone_offset = config.get_timezone_offset()

        logger.info(f"BinomClient initialized: {self.base_url} (timezone: {self.timezone_offset})")

    def _mask_api_key(self, url: str) -> str:
        """
        Маскирует API ключ в URL для безопасного логирования

        Args:
            url: URL с параметрами

        Returns:
            URL с замаскированным API ключом
        """
        if 'api_key=' in url:
            # Заменяем значение api_key на ***
            import re
            return re.sub(r'api_key=[^&]+', 'api_key=***', url)
        return url

    def _build_url(self, params: Dict[str, Any]) -> str:
        """
        Строит URL с параметрами

        Args:
            params: словарь параметров

        Returns:
            Полный URL
        """
        # Всегда добавляем API ключ
        params['api_key'] = self.api_key

        # Строим query string
        query_parts = [f"{k}={v}" for k, v in params.items()]
        query_string = "&".join(query_parts)

        # Binom API endpoint - custom путь для каждой установки
        # Если в base_url уже есть .php (has_api_path=True), не добавляем
        # Иначе используем дефолтный /index.php
        api_path = "" if self.has_api_path else "/index.php"

        return f"{self.base_url}{api_path}?{query_string}"

    def _request(self, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Выполняет HTTP запрос с retry механизмом

        Args:
            params: параметры запроса

        Returns:
            Ответ от API или None при ошибке
        """
        url = self._build_url(params)
        masked_url = self._mask_api_key(url)

        for attempt in range(self.retry_attempts):
            try:
                logger.debug(f"Request attempt {attempt + 1}/{self.retry_attempts}: {params.get('page')}")

                response = httpx.get(url, timeout=self.timeout)
                response.raise_for_status()

                # Пытаемся распарсить JSON
                try:
                    data = response.json()
                except ValueError as json_err:
                    # Если не получилось распарсить JSON - выводим текст ответа
                    logger.error(f"JSON parse error: {json_err}")
                    logger.error(f"Response text: {response.text[:500]}")
                    logger.error(f"Request URL: {masked_url}")
                    return None

                # Проверяем что получили валидный ответ
                # Проверяем различные варианты ошибок от API
                if isinstance(data, dict):
                    if 'error' in data:
                        logger.error(f"API error: {data['error']}")
                        return None
                    if 'status' in data and data['status'] == 'error':
                        logger.error(f"API error: {data.get('message', 'Unknown error')}")
                        return None

                # Проверяем что получили непустой ответ (список или dict)
                if data is None or (isinstance(data, list) and len(data) == 0):
                    logger.debug("Empty response from API (no data for this period/filter)")

                logger.debug(f"Request successful: {len(data) if isinstance(data, list) else 'dict'} items")
                return data

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout on attempt {attempt + 1}: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # Специальная обработка Rate Limiting (429)
                if status_code == 429:
                    logger.warning(f"Rate limit exceeded (429) on attempt {attempt + 1}")
                    if attempt < self.retry_attempts - 1:
                        # Для 429 используем увеличенную задержку
                        logger.info("Waiting 60 seconds before retry due to rate limiting...")
                        time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit exceeded, all retries exhausted")
                        return None

                logger.error(f"HTTP error {status_code}: {e}")

                # Повторяем при серверных ошибках (5xx)
                if status_code >= 500 and attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    return None

            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return None

        logger.error(f"All {self.retry_attempts} attempts failed for {masked_url}")
        return None

    def get_campaigns(
        self,
        date: str = "3",
        status: int = 2,
        val_page: str = "all",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Получает список кампаний

        Args:
            date: период для отчета:
                "1" - сегодня (PERIOD_TODAY)
                "2" - вчера (PERIOD_YESTERDAY)
                "3" - последние 7 дней (PERIOD_LAST_7_DAYS) - по умолчанию
                "4" - последние 14 дней (PERIOD_LAST_14_DAYS)
                "5" - текущий месяц (PERIOD_CURRENT_MONTH)
                "6" - прошлый месяц (PERIOD_LAST_MONTH)
                "12" - произвольный период (PERIOD_CUSTOM) - требует date_start и date_end
                "13" - последние 2 дня (PERIOD_LAST_2_DAYS)
                "14" - последние 3 дня (PERIOD_LAST_3_DAYS)
            status: статус кампаний (1=все, 2=с трафиком, 3=активные)
            val_page: 'all' для получения всех страниц, иначе только первая
            date_start: дата начала для произвольного периода (YYYY-MM-DD)
            date_end: дата окончания для произвольного периода (YYYY-MM-DD)

        Returns:
            Список кампаний или None при ошибке
        """
        params = {
            'page': 'Campaigns',
            'user_group': 'all',
            'status': status,
            'group': 'all',
            'traffic_source': 'all',
            'date': date,
            'timezone': self.timezone_offset,
            'val_page': val_page
        }

        # Для произвольного периода (date=12) добавляем date_s и date_e
        if date == "12" and date_start and date_end:
            params['date_s'] = date_start
            params['date_e'] = date_end
            logger.info(f"Getting campaigns: date=custom ({date_start} to {date_end}), status={status}, val_page={val_page}")
        else:
            logger.info(f"Getting campaigns: date={date}, status={status}, val_page={val_page}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} campaigns")
            return data

        logger.warning("Failed to retrieve campaigns")
        return None

    def get_campaign_stats(
        self,
        camp_id: int,
        date: str = "3",
        group1: str = "31",
        val_page: str = "all",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Получает статистику по кампании с группировкой

        Args:
            camp_id: ID кампании в Binom
            date: период для отчета (см. get_campaigns)
            group1: группировка:
                "31" - по датам (GROUP_BY_DATE) - по умолчанию
                "32" - по источникам (GROUP_BY_SOURCE)
                "33" - по странам (GROUP_BY_COUNTRY)
                "34" - по лендингам (GROUP_BY_LANDING)
                "35" - по офферам (GROUP_BY_OFFER)
            val_page: 'all' для получения всех страниц
            date_start: дата начала для произвольного периода (YYYY-MM-DD)
            date_end: дата окончания для произвольного периода (YYYY-MM-DD)

        Returns:
            Список статистики или None при ошибке
        """
        params = {
            'page': 'Stats',
            'camp_id': camp_id,
            'group1': group1,
            'group2': '1',
            'group3': '1',
            'date': date,
            'timezone': self.timezone_offset
        }

        # Для произвольного периода (date=12) добавляем date_s и date_e
        if date == "12" and date_start and date_end:
            params['date_s'] = date_start
            params['date_e'] = date_end
            logger.info(f"Getting stats for campaign {camp_id}: date=custom ({date_start} to {date_end}), group1={group1}")
        else:
            logger.info(f"Getting stats for campaign {camp_id}: date={date}, group1={group1}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} stats records for campaign {camp_id}")
            return data

        logger.warning(f"Failed to retrieve stats for campaign {camp_id}")
        return None

    def get_campaigns_custom_period(
        self,
        date_start: str,
        date_end: str,
        status: int = 2,
        val_page: str = "all"
    ) -> Optional[List[Dict]]:
        """
        Получает кампании за произвольный период

        Args:
            date_start: дата начала (формат: YYYY-MM-DD)
            date_end: дата окончания (формат: YYYY-MM-DD)
            status: статус (2=с трафиком за период)
            val_page: 'all' для получения всех страниц

        Returns:
            Список кампаний или None при ошибке
        """
        params = {
            'page': 'Campaigns',
            'user_group': 'all',
            'status': status,
            'group': 'all',
            'traffic_source': 'all',
            'date': '12',  # код для произвольного периода
            'timezone': self.timezone_offset,
            'date_e': date_end,
            'date_s': date_start,
            'val_page': val_page
        }

        logger.info(f"Getting campaigns: {date_start} to {date_end}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} campaigns for custom period")
            return data

        logger.warning("Failed to retrieve campaigns for custom period")
        return None

    def get_trends(
        self,
        date_trends: str = "4",
        date_gradation: str = "61"
    ) -> Optional[List[Dict]]:
        """
        Получает данные для графиков (разбивка по дням) из Trends API

        Args:
            date_trends: период для трендов:
                "3" - 7 дней (PERIOD_LAST_7_DAYS)
                "4" - 14 дней (PERIOD_LAST_14_DAYS) - по умолчанию
                "5" - месяц (PERIOD_CURRENT_MONTH)
            date_gradation: группировка:
                "61" - по дням (по умолчанию)
                "62" - по неделям
                "63" - по месяцам

        Returns:
            Список данных трендов по дням или None при ошибке
        """
        params = {
            'page': 'Trends',
            'date_gradation': date_gradation,
            'date_trends': date_trends,
            'timezone': self.timezone_offset
        }

        logger.info(f"Getting trends: date_trends={date_trends}, date_gradation={date_gradation}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} trend records")
            return data

        logger.warning("Failed to retrieve trends")
        return None

    def get_traffic_sources(
        self,
        date: str = "3",
        status: int = 2,
        val_page: str = "all",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Получает список источников трафика

        Args:
            date: период для отчета (см. get_campaigns)
            status: статус (1=все, 2=с трафиком за период)
            val_page: 'all' для получения всех страниц
            date_start: дата начала для произвольного периода (YYYY-MM-DD)
            date_end: дата окончания для произвольного периода (YYYY-MM-DD)

        Returns:
            Список источников трафика или None при ошибке
        """
        params = {
            'page': 'Traffic_Sources',
            'user_group': 'all',
            'status': status,
            'date': date,
            'timezone': self.timezone_offset,
            'val_page': val_page
        }

        # Для произвольного периода (date=12) добавляем date_s и date_e
        if date == "12" and date_start and date_end:
            params['date_s'] = date_start
            params['date_e'] = date_end
            logger.info(f"Getting traffic sources: date=custom ({date_start} to {date_end}), status={status}")
        else:
            logger.info(f"Getting traffic sources: date={date}, status={status}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} traffic sources")
            return data

        logger.warning("Failed to retrieve traffic sources")
        return None

    def get_affiliate_networks(
        self,
        date: str = "3",
        status: int = 2,
        val_page: str = "all",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Получает список партнерских сетей

        Args:
            date: период для отчета (см. get_campaigns)
            status: статус (1=все, 2=с трафиком за период)
            val_page: 'all' для получения всех страниц
            date_start: дата начала для произвольного периода (YYYY-MM-DD)
            date_end: дата окончания для произвольного периода (YYYY-MM-DD)

        Returns:
            Список партнерских сетей или None при ошибке
        """
        params = {
            'page': 'Affiliate_Networks',
            'user_group': 'all',
            'status': status,
            'date': date,
            'timezone': self.timezone_offset,
            'val_page': val_page
        }

        # Для произвольного периода (date=12) добавляем date_s и date_e
        if date == "12" and date_start and date_end:
            params['date_s'] = date_start
            params['date_e'] = date_end
            logger.info(f"Getting affiliate networks: date=custom ({date_start} to {date_end}), status={status}")
        else:
            logger.info(f"Getting affiliate networks: date={date}, status={status}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} affiliate networks")
            return data

        logger.warning("Failed to retrieve affiliate networks")
        return None

    def get_offers(
        self,
        date: str = "3",
        status: int = 2,
        val_page: str = "all",
        networks_filter: str = "all",
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Получает список офферов

        Args:
            date: период для отчета (см. get_campaigns)
            status: статус (1=все, 2=с трафиком за период)
            val_page: 'all' для получения всех страниц
            networks_filter: фильтр по партнерским сетям ('all' или ID сети)
            date_start: дата начала для произвольного периода (YYYY-MM-DD)
            date_end: дата окончания для произвольного периода (YYYY-MM-DD)

        Returns:
            Список офферов или None при ошибке
        """
        params = {
            'page': 'Offers',
            'user_group': 'all',
            'status': status,
            'group': 'all',
            'networks_filter': networks_filter,
            'date': date,
            'timezone': self.timezone_offset,
            'val_page': val_page
        }

        # Для произвольного периода (date=12) добавляем date_s и date_e
        if date == "12" and date_start and date_end:
            params['date_s'] = date_start
            params['date_e'] = date_end
            logger.info(f"Getting offers: date=custom ({date_start} to {date_end}), status={status}")
        else:
            logger.info(f"Getting offers: date={date}, status={status}")

        data = self._request(params)

        if data and isinstance(data, list):
            logger.info(f"Retrieved {len(data)} offers")
            return data

        logger.warning("Failed to retrieve offers")
        return None

    def test_connection(self) -> bool:
        """
        Проверяет соединение с Binom API

        Returns:
            True если соединение успешно, иначе False
        """
        logger.info("Testing connection to Binom API")

        # Пытаемся получить данные за сегодня (минимальный запрос)
        data = self.get_campaigns(date="1", val_page="1")

        if data is not None:
            logger.info("[OK] Connection test successful")
            return True
        else:
            logger.error("[FAIL] Connection test failed")
            return False
