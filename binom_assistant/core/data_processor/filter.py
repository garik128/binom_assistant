"""
Фильтрация незначимых кампаний (шума)

Для анализа сотен мелких кампаний нужно отсеивать совсем мелкие.
Игнорируем кампании с расходом < 1$ ИЛИ < 50 кликов за период.
"""
import logging
from typing import Dict, Any, List
from datetime import date, timedelta

from storage.database import session_scope, Campaign, CampaignStatsDaily
from sqlalchemy import func


logger = logging.getLogger(__name__)


# Пороги значимости
MIN_DAILY_SPEND = 1.0  # минимальный расход в день
MIN_CLICKS = 50        # минимальное количество кликов за период


def is_significant_campaign(
    campaign_data: Dict[str, Any],
    min_spend: float = MIN_DAILY_SPEND,
    min_clicks: int = MIN_CLICKS
) -> bool:
    """
    Проверяет значимость кампании для анализа

    Кампания значима если:
    - Расход >= min_spend ИЛИ
    - Клики >= min_clicks

    Args:
        campaign_data: данные кампании
        min_spend: минимальный расход
        min_clicks: минимальное количество кликов

    Returns:
        True если значима, False если шум
    """
    cost = float(campaign_data.get('cost', 0))
    clicks = int(campaign_data.get('clicks', 0))

    is_significant = cost >= min_spend or clicks >= min_clicks

    if not is_significant:
        logger.debug(
            f"Campaign {campaign_data.get('id')} filtered out: "
            f"cost={cost}, clicks={clicks}"
        )

    return is_significant


def filter_significant_campaigns(
    campaigns: List[Dict[str, Any]],
    min_spend: float = MIN_DAILY_SPEND,
    min_clicks: int = MIN_CLICKS
) -> List[Dict[str, Any]]:
    """
    Фильтрует список кампаний, оставляя только значимые

    Args:
        campaigns: список кампаний
        min_spend: минимальный расход
        min_clicks: минимальное количество кликов

    Returns:
        Отфильтрованный список
    """
    significant = [
        camp for camp in campaigns
        if is_significant_campaign(camp, min_spend, min_clicks)
    ]

    logger.info(
        f"Filtered campaigns: {len(campaigns)} -> {len(significant)} "
        f"({len(campaigns) - len(significant)} filtered out)"
    )

    return significant


def get_significant_campaigns_from_db(
    days: int = 7,
    min_spend: float = MIN_DAILY_SPEND,
    min_clicks: int = MIN_CLICKS
) -> List[Campaign]:
    """
    Получает значимые кампании из БД за период

    Args:
        days: количество дней для анализа
        min_spend: минимальный расход за период
        min_clicks: минимальное количество кликов за период

    Returns:
        Список значимых кампаний
    """
    # Включаем текущий день: для 7 дней это сегодня минус 6 дней
    start_date = date.today() - timedelta(days=days - 1)
    end_date = date.today()

    with session_scope() as session:
        # Получаем кампании с агрегированной статистикой
        campaigns_with_stats = session.query(
            Campaign,
            func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
            func.sum(CampaignStatsDaily.cost).label('total_cost')
        ).join(
            CampaignStatsDaily,
            Campaign.internal_id == CampaignStatsDaily.campaign_id
        ).filter(
            CampaignStatsDaily.date >= start_date,
            CampaignStatsDaily.date <= end_date
        ).group_by(
            Campaign.internal_id
        ).all()

        # Фильтруем
        significant = []
        for campaign, total_clicks, total_cost in campaigns_with_stats:
            total_cost = float(total_cost) if total_cost else 0
            total_clicks = int(total_clicks) if total_clicks else 0

            if total_cost >= min_spend or total_clicks >= min_clicks:
                significant.append(campaign)

        logger.info(
            f"Found {len(significant)} significant campaigns "
            f"out of {len(campaigns_with_stats)}"
        )

        return significant


def calculate_noise_stats(
    campaigns: List[Dict[str, Any]],
    min_spend: float = MIN_DAILY_SPEND,
    min_clicks: int = MIN_CLICKS
) -> Dict[str, Any]:
    """
    Рассчитывает статистику по шуму

    Args:
        campaigns: список всех кампаний
        min_spend: минимальный расход
        min_clicks: минимальное количество кликов

    Returns:
        Словарь со статистикой
    """
    significant = []
    noise = []

    for camp in campaigns:
        if is_significant_campaign(camp, min_spend, min_clicks):
            significant.append(camp)
        else:
            noise.append(camp)

    # Считаем метрики
    noise_revenue = sum(float(c.get('revenue', 0)) for c in noise)
    noise_cost = sum(float(c.get('cost', 0)) for c in noise)

    total_revenue = sum(float(c.get('revenue', 0)) for c in campaigns)
    total_cost = sum(float(c.get('cost', 0)) for c in campaigns)

    stats = {
        'total_campaigns': len(campaigns),
        'significant_campaigns': len(significant),
        'noise_campaigns': len(noise),
        'noise_percentage': len(noise) / len(campaigns) * 100 if campaigns else 0,
        'noise_revenue': noise_revenue,
        'noise_cost': noise_cost,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'noise_revenue_share': noise_revenue / total_revenue * 100 if total_revenue > 0 else 0,
        'noise_cost_share': noise_cost / total_cost * 100 if total_cost > 0 else 0,
    }

    return stats
