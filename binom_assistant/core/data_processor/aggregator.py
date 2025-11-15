"""
Агрегация данных по неделям

Для мелких кампаний дневные данные слишком шумные.
Недельная агрегация дает более стабильную картину.
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import func

from storage.database import (
    session_scope,
    Campaign,
    CampaignStatsDaily,
    StatWeekly
)


logger = logging.getLogger(__name__)


def get_week_start(target_date: date) -> date:
    """
    Получает понедельник недели для заданной даты

    Args:
        target_date: дата

    Returns:
        Дата понедельника этой недели
    """
    # weekday(): 0 = Monday, 6 = Sunday
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)
    return week_start


def get_week_end(week_start: date) -> date:
    """
    Получает воскресенье недели

    Args:
        week_start: понедельник недели

    Returns:
        Дата воскресенья этой недели
    """
    return week_start + timedelta(days=6)


def aggregate_weekly_stats(
    campaign_id: Optional[int] = None,
    week_start: Optional[date] = None
) -> int:
    """
    Агрегирует дневную статистику в недельную

    Args:
        campaign_id: ID кампании (None = все кампании)
        week_start: начало недели (None = текущая неделя)

    Returns:
        Количество созданных/обновленных записей
    """
    logger.info(f"Aggregating weekly stats for campaign {campaign_id or 'ALL'}")

    # Определяем неделю
    if week_start is None:
        week_start = get_week_start(date.today())

    week_end = get_week_end(week_start)

    logger.info(f"Week: {week_start} - {week_end}")

    count = 0

    with session_scope() as session:
        # Получаем кампании для агрегации
        query = session.query(Campaign)
        if campaign_id:
            query = query.filter(Campaign.internal_id == campaign_id)

        campaigns = query.all()

        logger.info(f"Processing {len(campaigns)} campaigns")

        # Ранний выход при отсутствии кампаний
        if not campaigns:
            logger.info("No campaigns to process")
            return 0

        for campaign in campaigns:
            # Получаем дневную статистику за эту неделю
            daily_stats = session.query(CampaignStatsDaily).filter(
                CampaignStatsDaily.campaign_id == campaign.internal_id,
                CampaignStatsDaily.date >= week_start,
                CampaignStatsDaily.date <= week_end
            ).all()

            if not daily_stats:
                continue

            # Агрегируем
            total_clicks = sum(s.clicks if s.clicks else 0 for s in daily_stats)
            total_leads = sum(s.leads if s.leads else 0 for s in daily_stats)
            total_cost = sum(float(s.cost) if s.cost else 0 for s in daily_stats)
            total_revenue = sum(float(s.revenue) if s.revenue else 0 for s in daily_stats)
            total_profit = total_revenue - total_cost

            total_a_leads = sum(s.a_leads if s.a_leads else 0 for s in daily_stats)
            total_h_leads = sum(s.h_leads if s.h_leads else 0 for s in daily_stats)
            total_r_leads = sum(s.r_leads if s.r_leads else 0 for s in daily_stats)

            # Средние значения (только по дням с данными)
            days_with_data = len([s for s in daily_stats if s.clicks > 0])

            if days_with_data > 0:
                avg_roi = (total_profit / total_cost * 100) if total_cost > 0 else 0
                avg_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0
                avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
                avg_approve = (total_a_leads / total_leads * 100) if total_leads > 0 else 0
            else:
                avg_roi = avg_cr = avg_cpc = avg_approve = 0

            # Ищем существующую запись
            existing = session.query(StatWeekly).filter_by(
                campaign_id=campaign.internal_id,
                week_start=week_start
            ).first()

            if existing:
                # Обновляем
                existing.week_end = week_end
                existing.total_clicks = total_clicks
                existing.total_leads = total_leads
                existing.total_cost = total_cost
                existing.total_revenue = total_revenue
                existing.total_profit = total_profit
                existing.avg_roi = avg_roi
                existing.avg_cr = avg_cr
                existing.avg_cpc = avg_cpc
                existing.avg_approve = avg_approve
                existing.total_a_leads = total_a_leads
                existing.total_h_leads = total_h_leads
                existing.total_r_leads = total_r_leads

                logger.debug(f"Updated weekly stats for campaign {campaign.binom_id}")
            else:
                # Создаем новую
                weekly_stat = StatWeekly(
                    campaign_id=campaign.internal_id,
                    week_start=week_start,
                    week_end=week_end,
                    total_clicks=total_clicks,
                    total_leads=total_leads,
                    total_cost=total_cost,
                    total_revenue=total_revenue,
                    total_profit=total_profit,
                    avg_roi=avg_roi,
                    avg_cr=avg_cr,
                    avg_cpc=avg_cpc,
                    avg_approve=avg_approve,
                    total_a_leads=total_a_leads,
                    total_h_leads=total_h_leads,
                    total_r_leads=total_r_leads
                )

                session.add(weekly_stat)
                logger.debug(f"Created weekly stats for campaign {campaign.binom_id}")

            count += 1

        session.commit()

    logger.info(f"Aggregated weekly stats for {count} campaigns")
    return count


def get_weekly_stats_for_campaign(
    campaign_id: int,
    weeks: int = 4
) -> List[Dict[str, Any]]:
    """
    Получает недельную статистику для кампании

    Args:
        campaign_id: internal_id кампании
        weeks: количество недель (от текущей назад)

    Returns:
        Список словарей с недельной статистикой
    """
    current_week_start = get_week_start(date.today())

    with session_scope() as session:
        stats = session.query(StatWeekly).filter(
            StatWeekly.campaign_id == campaign_id,
            StatWeekly.week_start <= current_week_start
        ).order_by(
            StatWeekly.week_start.desc()
        ).limit(weeks).all()

        return [
            {
                'week_start': s.week_start,
                'week_end': s.week_end,
                'clicks': s.total_clicks,
                'leads': s.total_leads,
                'cost': float(s.total_cost),
                'revenue': float(s.total_revenue),
                'profit': float(s.total_profit),
                'roi': float(s.avg_roi) if s.avg_roi else 0,
                'cr': float(s.avg_cr) if s.avg_cr else 0,
                'cpc': float(s.avg_cpc) if s.avg_cpc else 0,
            }
            for s in stats
        ]
