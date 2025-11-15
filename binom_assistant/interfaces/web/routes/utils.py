# -*- coding: utf-8 -*-
"""
Вспомогательные функции для работы с периодами.
"""
from datetime import timedelta


def get_date_range_for_period(period: str):
    """
    Получить диапазон дат для периода.

    Args:
        period: Период (1d, yesterday, 7d, 14d, 30d, this_month, last_month)

    Returns:
        tuple: (date_from, date_to)
    """
    from datetime import date as dt_date
    from calendar import monthrange

    today = dt_date.today()

    if period == '1d':
        # Сегодня
        return today, today

    elif period == 'yesterday':
        # Вчера
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    elif period.endswith('d'):
        # 7d, 14d, 30d
        days = int(period.replace('d', ''))
        date_from = today - timedelta(days=days - 1)
        return date_from, today

    elif period == 'this_month':
        # Этот месяц (с 1-го по сегодня включительно)
        date_from = today.replace(day=1)
        return date_from, today

    elif period == 'last_month':
        # Прошлый месяц (полный)
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        return first_day_last_month, last_day_last_month

    else:
        # По умолчанию - 7 дней
        date_from = today - timedelta(days=6)
        return date_from, today


def should_use_stat_period(period: str) -> bool:
    """
    Определить, нужно ли использовать StatPeriod (агрегированные данные).

    Используем StatPeriod только для стандартных периодов (7d, 14d, 30d),
    для которых есть предвычисленные агрегаты.

    Для остальных периодов читаем из CampaignStatsDaily напрямую.

    Args:
        period: Период

    Returns:
        bool: True если нужно использовать StatPeriod, False - CampaignStatsDaily
    """
    return period in ['7d', '14d', '30d']
