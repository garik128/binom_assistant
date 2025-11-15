"""
Модуль для очистки сырых данных от Binom API

Задача: убрать лишние поля, оставить только нужные
"""
import logging
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)


# Список нужных полей для кампаний
CAMPAIGN_FIELDS = [
    'id',
    'name',
    'domain_name',
    'group_name',
    'ts_name',
    'clicks',
    'leads',
    'revenue',
    'cost',
    'approve',
    'a_leads',
    'h_leads',
    'r_leads',
    'lead',  # цена лида
    'profit',
    'roi',
    'cr',
    'epc',
    'cpc'
]

# Список нужных полей для статистики
STATS_FIELDS = [
    'name',  # обычно это дата или название группы
    'clicks',
    'leads',
    'cost',
    'revenue',
    'cr',
    'cpc',
    'profit',
    'roi',
    'a_leads',
    'approve',
    'r_leads',
    'h_leads',
    'lead',  # цена лида
    'epc'
]


def clean_campaign_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает данные кампании от лишних полей

    ВАЖНО: Обработка пустых значений
    -------------------------------------
    Пустая строка ('') от Binom API означает "нет данных" и конвертируется в 0
    для числовых полей. Это правильное решение, потому что:
    1. В контексте метрик '' и 0 означают одно и то же - отсутствие значения
    2. Использование None усложнило бы математические операции в CPL detector
    3. CPL detector различает кампании по наличию/отсутствию апрувов (0 vs >0),
       а не по None vs 0

    Args:
        raw_data: сырые данные от Binom API

    Returns:
        Очищенный словарь с нужными полями
    """
    cleaned = {}

    for field in CAMPAIGN_FIELDS:
        if field in raw_data:
            # Получаем значение
            value = raw_data[field]

            # Конвертируем пустые строки в 0 для числовых полей
            # (для строковых полей оставляем пустую строку)
            if value == '' and field not in ['name', 'domain_name', 'group_name', 'ts_name']:
                value = 0

            cleaned[field] = value
        else:
            # Если поле отсутствует, ставим дефолтное значение
            if field in ['name', 'domain_name', 'group_name', 'ts_name']:
                cleaned[field] = ''
            else:
                cleaned[field] = 0

    return cleaned


def clean_campaign_stats(raw_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает статистику кампании от лишних полей

    Примечание: Пустые строки ('') конвертируются в 0 для числовых полей.
    См. комментарии в clean_campaign_data() для объяснения этого решения.

    Args:
        raw_stats: сырые данные статистики от Binom API

    Returns:
        Очищенный словарь с нужными полями
    """
    cleaned = {}

    for field in STATS_FIELDS:
        if field in raw_stats:
            value = raw_stats[field]

            # Конвертируем пустые строки в 0 для числовых полей
            if value == '' and field != 'name':
                value = 0

            cleaned[field] = value
        else:
            # Дефолтное значение
            if field == 'name':
                cleaned[field] = ''
            else:
                cleaned[field] = 0

    return cleaned


def clean_campaigns_list(campaigns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Очищает список кампаний

    Args:
        campaigns: список сырых данных кампаний

    Returns:
        Список очищенных кампаний
    """
    if not campaigns:
        return []

    cleaned_list = []

    for campaign in campaigns:
        cleaned = clean_campaign_data(campaign)
        cleaned_list.append(cleaned)

    logger.debug(f"Cleaned {len(cleaned_list)} campaigns")
    return cleaned_list


def clean_stats_list(stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Очищает список статистики

    Args:
        stats: список сырых данных статистики

    Returns:
        Список очищенной статистики
    """
    if not stats:
        return []

    cleaned_list = []

    for stat in stats:
        cleaned = clean_campaign_stats(stat)
        cleaned_list.append(cleaned)

    logger.debug(f"Cleaned {len(cleaned_list)} stats records")
    return cleaned_list


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Безопасно конвертирует значение в float

    Args:
        value: значение для конвертации
        default: значение по умолчанию

    Returns:
        float значение или default
    """
    try:
        if value == '' or value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Безопасно конвертирует значение в int

    Args:
        value: значение для конвертации
        default: значение по умолчанию

    Returns:
        int значение или default
    """
    try:
        if value == '' or value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def normalize_campaign_data(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует данные кампании (типы данных)

    Args:
        campaign: данные кампании

    Returns:
        Нормализованный словарь
    """
    normalized = campaign.copy()

    # Целочисленные поля
    int_fields = ['id', 'clicks', 'leads', 'a_leads', 'h_leads', 'r_leads']
    for field in int_fields:
        if field in normalized:
            normalized[field] = safe_int(normalized[field])

    # Числовые поля с плавающей точкой
    float_fields = ['revenue', 'cost', 'roi', 'cr', 'epc', 'cpc', 'lead', 'profit', 'approve']
    for field in float_fields:
        if field in normalized:
            normalized[field] = safe_float(normalized[field])

    # Строковые поля
    str_fields = ['name', 'domain_name', 'group_name', 'ts_name']
    for field in str_fields:
        if field in normalized:
            if normalized[field] is None:
                normalized[field] = ''
            else:
                normalized[field] = str(normalized[field])

    return normalized


def normalize_stats_data(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует данные статистики (типы данных)

    Args:
        stats: данные статистики

    Returns:
        Нормализованный словарь
    """
    normalized = stats.copy()

    # Целочисленные поля
    int_fields = ['clicks', 'leads', 'a_leads', 'h_leads', 'r_leads']
    for field in int_fields:
        if field in normalized:
            normalized[field] = safe_int(normalized[field])

    # Числовые поля с плавающей точкой
    float_fields = ['revenue', 'cost', 'roi', 'cr', 'epc', 'cpc', 'lead', 'profit', 'approve']
    for field in float_fields:
        if field in normalized:
            normalized[field] = safe_float(normalized[field])

    # Строковое поле name (дата или группа)
    if 'name' in normalized:
        if normalized['name'] is None:
            normalized['name'] = ''
        else:
            normalized['name'] = str(normalized['name'])

    return normalized


def get_field_summary(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Получает сводку по полям (для отладки)

    Args:
        data: словарь данных

    Returns:
        Словарь с типами полей
    """
    summary = {}

    for key, value in data.items():
        summary[key] = type(value).__name__

    return summary


# Список нужных полей для источников трафика
TRAFFIC_SOURCE_FIELDS = [
    'id',
    'name',
    'status',
    'clicks',
    'cost',
    'leads',
    'revenue',
    'roi',
    'cr',
    'cpc',
    'a_leads',
    'h_leads',
    'r_leads',
    'approve'
]

# Список нужных полей для партнерских сетей
AFFILIATE_NETWORK_FIELDS = [
    'id',
    'name',
    'status',
    'clicks',
    'leads',
    'revenue',
    'cost',
    'a_leads',
    'h_leads',
    'r_leads',
    'approve',
    'roi',
    'profit',
    'offers'
]

# Список нужных полей для офферов
OFFER_FIELDS = [
    'id',
    'name',
    'network_id',
    'geo',
    'payout',
    'clicks',
    'leads',
    'revenue',
    'cost',
    'a_leads',
    'h_leads',
    'r_leads',
    'cr',
    'approve',
    'epc',
    'roi',
    'status'
]


def clean_traffic_source_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает данные источника трафика от лишних полей

    Args:
        raw_data: сырые данные от Binom API

    Returns:
        Очищенный словарь с нужными полями
    """
    cleaned = {}

    for field in TRAFFIC_SOURCE_FIELDS:
        if field in raw_data:
            value = raw_data[field]
            # Конвертируем пустые строки в 0 для числовых полей
            if value == '' and field not in ['name']:
                value = 0
            cleaned[field] = value
        else:
            # Дефолтное значение
            if field in ['name']:
                cleaned[field] = ''
            elif field in ['status']:
                cleaned[field] = True  # активен по умолчанию
            else:
                cleaned[field] = 0

    return cleaned


def clean_affiliate_network_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает данные партнерской сети от лишних полей

    Args:
        raw_data: сырые данные от Binom API

    Returns:
        Очищенный словарь с нужными полями
    """
    cleaned = {}

    for field in AFFILIATE_NETWORK_FIELDS:
        if field in raw_data:
            value = raw_data[field]
            # Конвертируем пустые строки в 0 для числовых полей
            if value == '' and field not in ['name']:
                value = 0
            cleaned[field] = value
        else:
            # Дефолтное значение
            if field in ['name']:
                cleaned[field] = ''
            elif field in ['status']:
                cleaned[field] = True  # активен по умолчанию
            else:
                cleaned[field] = 0

    return cleaned


def clean_offer_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очищает данные оффера от лишних полей

    Args:
        raw_data: сырые данные от Binom API

    Returns:
        Очищенный словарь с нужными полями
    """
    cleaned = {}

    for field in OFFER_FIELDS:
        if field in raw_data:
            value = raw_data[field]
            # Конвертируем пустые строки в 0 для числовых полей
            if value == '' and field not in ['name', 'geo']:
                value = 0
            cleaned[field] = value
        else:
            # Дефолтное значение
            if field in ['name', 'geo']:
                cleaned[field] = ''
            elif field in ['status']:
                cleaned[field] = True  # активен по умолчанию
            else:
                cleaned[field] = 0

    return cleaned


def clean_traffic_sources_list(traffic_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Очищает список источников трафика

    Args:
        traffic_sources: список сырых данных источников трафика

    Returns:
        Список очищенных источников
    """
    if not traffic_sources:
        return []

    cleaned_list = []
    for ts in traffic_sources:
        cleaned = clean_traffic_source_data(ts)
        cleaned_list.append(cleaned)

    logger.debug(f"Cleaned {len(cleaned_list)} traffic sources")
    return cleaned_list


def clean_affiliate_networks_list(networks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Очищает список партнерских сетей

    Args:
        networks: список сырых данных партнерок

    Returns:
        Список очищенных сетей
    """
    if not networks:
        return []

    cleaned_list = []
    for network in networks:
        cleaned = clean_affiliate_network_data(network)
        cleaned_list.append(cleaned)

    logger.debug(f"Cleaned {len(cleaned_list)} affiliate networks")
    return cleaned_list


def clean_offers_list(offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Очищает список офферов

    Args:
        offers: список сырых данных офферов

    Returns:
        Список очищенных офферов
    """
    if not offers:
        return []

    cleaned_list = []
    for offer in offers:
        cleaned = clean_offer_data(offer)
        cleaned_list.append(cleaned)

    logger.debug(f"Cleaned {len(cleaned_list)} offers")
    return cleaned_list


def normalize_traffic_source_data(ts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует данные источника трафика (типы данных)

    Args:
        ts: данные источника трафика

    Returns:
        Нормализованный словарь
    """
    normalized = ts.copy()

    # Целочисленные поля
    int_fields = ['id', 'clicks', 'leads', 'a_leads', 'h_leads', 'r_leads']
    for field in int_fields:
        if field in normalized:
            normalized[field] = safe_int(normalized[field])

    # Числовые поля с плавающей точкой
    float_fields = ['cost', 'revenue', 'roi', 'cr', 'cpc', 'approve']
    for field in float_fields:
        if field in normalized:
            normalized[field] = safe_float(normalized[field])

    # Строковые поля
    if 'name' in normalized:
        normalized['name'] = str(normalized['name']) if normalized['name'] is not None else ''

    # Boolean поле
    if 'status' in normalized:
        normalized['status'] = bool(normalized['status'])

    return normalized


def normalize_affiliate_network_data(network: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует данные партнерской сети (типы данных)

    Args:
        network: данные партнерки

    Returns:
        Нормализованный словарь
    """
    normalized = network.copy()

    # Целочисленные поля
    int_fields = ['id', 'clicks', 'leads', 'a_leads', 'h_leads', 'r_leads', 'offers']
    for field in int_fields:
        if field in normalized:
            normalized[field] = safe_int(normalized[field])

    # Числовые поля с плавающей точкой
    float_fields = ['revenue', 'cost', 'approve', 'roi', 'profit']
    for field in float_fields:
        if field in normalized:
            normalized[field] = safe_float(normalized[field])

    # Строковые поля
    if 'name' in normalized:
        normalized['name'] = str(normalized['name']) if normalized['name'] is not None else ''

    # Boolean поле
    if 'status' in normalized:
        normalized['status'] = bool(normalized['status'])

    return normalized


def normalize_offer_data(offer: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует данные оффера (типы данных)

    Args:
        offer: данные оффера

    Returns:
        Нормализованный словарь
    """
    normalized = offer.copy()

    # Целочисленные поля
    int_fields = ['id', 'network_id', 'clicks', 'leads', 'a_leads', 'h_leads', 'r_leads']
    for field in int_fields:
        if field in normalized:
            normalized[field] = safe_int(normalized[field])

    # Числовые поля с плавающей точкой
    float_fields = ['payout', 'revenue', 'cost', 'cr', 'approve', 'epc', 'roi']
    for field in float_fields:
        if field in normalized:
            normalized[field] = safe_float(normalized[field])

    # Строковые поля
    str_fields = ['name', 'geo']
    for field in str_fields:
        if field in normalized:
            normalized[field] = str(normalized[field]) if normalized[field] is not None else ''

    # Boolean поле
    if 'status' in normalized:
        normalized['status'] = bool(normalized['status'])

    return normalized
