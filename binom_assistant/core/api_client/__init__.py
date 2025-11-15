"""
Модуль для работы с Binom API
"""
from .client import BinomClient
from .data_cleaner import (
    clean_campaign_data,
    clean_campaign_stats,
    clean_campaigns_list,
    clean_stats_list,
    normalize_campaign_data,
    normalize_stats_data,
    clean_traffic_sources_list,
    clean_affiliate_networks_list,
    clean_offers_list,
    normalize_traffic_source_data,
    normalize_affiliate_network_data,
    normalize_offer_data
)
from .cpl_detector import CPLDetector, detect_campaign_type
from .constants import (
    PERIOD_TODAY,
    PERIOD_YESTERDAY,
    PERIOD_LAST_7_DAYS,
    PERIOD_LAST_14_DAYS,
    PERIOD_CURRENT_MONTH,
    PERIOD_LAST_MONTH,
    PERIOD_CUSTOM,
    PERIOD_LAST_2_DAYS,
    PERIOD_LAST_3_DAYS,
    PERIOD_MAP,
    PERIOD_NAME_MAP,
    STATUS_ALL,
    STATUS_WITH_TRAFFIC,
    STATUS_ACTIVE,
    GROUP_BY_DATE,
    GROUP_BY_SOURCE,
    GROUP_BY_COUNTRY,
    GROUP_BY_LANDING,
    GROUP_BY_OFFER
)

__all__ = [
    'BinomClient',
    'clean_campaign_data',
    'clean_campaign_stats',
    'clean_campaigns_list',
    'clean_stats_list',
    'normalize_campaign_data',
    'normalize_stats_data',
    'clean_traffic_sources_list',
    'clean_affiliate_networks_list',
    'clean_offers_list',
    'normalize_traffic_source_data',
    'normalize_affiliate_network_data',
    'normalize_offer_data',
    'CPLDetector',
    'detect_campaign_type',
    # Constants
    'PERIOD_TODAY',
    'PERIOD_YESTERDAY',
    'PERIOD_LAST_7_DAYS',
    'PERIOD_LAST_14_DAYS',
    'PERIOD_CURRENT_MONTH',
    'PERIOD_LAST_MONTH',
    'PERIOD_CUSTOM',
    'PERIOD_LAST_2_DAYS',
    'PERIOD_LAST_3_DAYS',
    'PERIOD_MAP',
    'PERIOD_NAME_MAP',
    'STATUS_ALL',
    'STATUS_WITH_TRAFFIC',
    'STATUS_ACTIVE',
    'GROUP_BY_DATE',
    'GROUP_BY_SOURCE',
    'GROUP_BY_COUNTRY',
    'GROUP_BY_LANDING',
    'GROUP_BY_OFFER',
]
