"""
Утилита для пересчета stat_periods из campaign_stats_daily

Агрегирует дневные данные в периодные для быстрого доступа:
- 7days: последние 7 дней
- 14days: последние 14 дней
- 30days: последние 30 дней

Использование:
    from services.scheduler.aggregate_periods import recalculate_stat_periods
    recalculate_stat_periods()
"""
import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from utils.datetime_utils import get_now
from storage.database import (
    session_scope,
    Campaign,
    CampaignStatsDaily,
    StatPeriod
)

logger = logging.getLogger(__name__)


def _calculate_metrics(clicks: int, leads: int, cost: float, revenue: float,
                       a_leads: int, h_leads: int, r_leads: int) -> Dict[str, Optional[float]]:
    """
    Вычисляет производные метрики

    Args:
        clicks: количество кликов
        leads: общее количество лидов
        cost: расходы
        revenue: доходы
        a_leads: апрувленные лиды
        h_leads: холд лиды
        r_leads: отклоненные лиды

    Returns:
        Словарь с метриками: roi, cr, cpc, approve, lead_price, profit, epc
    """
    metrics = {
        'roi': None,
        'cr': None,
        'cpc': None,
        'approve': None,
        'lead_price': None,
        'profit': None,
        'epc': None
    }

    # ROI (%)
    if cost > 0:
        metrics['roi'] = ((revenue - cost) / cost) * 100

    # CR (%) - Conversion Rate
    if clicks > 0:
        metrics['cr'] = (leads / clicks) * 100

    # CPC - Cost Per Click
    if clicks > 0:
        metrics['cpc'] = cost / clicks

    # Approve (%) - процент апрува
    total_processed = a_leads + h_leads + r_leads
    if total_processed > 0:
        metrics['approve'] = (a_leads / total_processed) * 100

    # Lead Price - стоимость лида
    if leads > 0:
        metrics['lead_price'] = cost / leads

    # Profit
    metrics['profit'] = revenue - cost

    # EPC - Earnings Per Click
    if clicks > 0:
        metrics['epc'] = revenue / clicks

    return metrics


def aggregate_period_for_campaign(
    session,
    campaign_id: int,
    period_type: str,
    period_start: date,
    period_end: date
) -> Optional[Dict[str, Any]]:
    """
    Агрегирует дневную статистику для одной кампании за период

    Args:
        session: активная сессия SQLAlchemy
        campaign_id: internal_id кампании
        period_type: тип периода ('7days', '14days', '30days')
        period_start: начало периода
        period_end: конец периода

    Returns:
        Словарь с агрегированными данными или None если нет данных
    """
    # Агрегируем дневные данные
    result = session.query(
        func.sum(CampaignStatsDaily.clicks).label('clicks'),
        func.sum(CampaignStatsDaily.leads).label('leads'),
        func.sum(CampaignStatsDaily.cost).label('cost'),
        func.sum(CampaignStatsDaily.revenue).label('revenue'),
        func.sum(CampaignStatsDaily.a_leads).label('a_leads'),
        func.sum(CampaignStatsDaily.h_leads).label('h_leads'),
        func.sum(CampaignStatsDaily.r_leads).label('r_leads')
    ).filter(
        CampaignStatsDaily.campaign_id == campaign_id,
        CampaignStatsDaily.date >= period_start,
        CampaignStatsDaily.date <= period_end
    ).first()

    # Если нет данных - возвращаем None
    if not result or result.clicks is None:
        return None

    # Распаковываем результат
    clicks = result.clicks or 0
    leads = result.leads or 0
    cost = float(result.cost or 0)
    revenue = float(result.revenue or 0)
    a_leads = result.a_leads or 0
    h_leads = result.h_leads or 0
    r_leads = result.r_leads or 0

    # Вычисляем производные метрики
    metrics = _calculate_metrics(clicks, leads, cost, revenue, a_leads, h_leads, r_leads)

    return {
        'campaign_id': campaign_id,
        'period_type': period_type,
        'period_start': period_start,
        'period_end': period_end,
        'clicks': clicks,
        'leads': leads,
        'cost': cost,
        'revenue': revenue,
        'a_leads': a_leads,
        'h_leads': h_leads,
        'r_leads': r_leads,
        'roi': metrics['roi'],
        'cr': metrics['cr'],
        'cpc': metrics['cpc'],
        'approve': metrics['approve'],
        'lead_price': metrics['lead_price'],
        'profit': metrics['profit'],
        'epc': metrics['epc'],
        'snapshot_time': get_now()
    }


def recalculate_stat_periods(periods: List[str] = None) -> Dict[str, Any]:
    """
    Пересчитывает stat_periods для всех кампаний

    Args:
        periods: список периодов для пересчета (по умолчанию все: 7days, 14days, 30days)

    Returns:
        Статистика пересчета:
        {
            'periods_processed': int,
            'campaigns_processed': int,
            'records_created': int,
            'records_updated': int,
            'records_deleted': int,
            'errors': []
        }
    """
    if periods is None:
        periods = ['7days', '14days', '30days']

    logger.info("=" * 60)
    logger.info("Starting stat_periods recalculation")
    logger.info(f"Periods: {', '.join(periods)}")
    logger.info("=" * 60)

    stats = {
        'periods_processed': 0,
        'campaigns_processed': 0,
        'records_created': 0,
        'records_updated': 0,
        'records_deleted': 0,
        'errors': []
    }

    # Маппинг периодов в количество дней
    period_days = {
        '7days': 7,
        '14days': 14,
        '30days': 30
    }

    today = date.today()

    with session_scope() as session:
        # Получаем все активные кампании
        campaigns = session.query(Campaign).filter(Campaign.is_active == True).all()

        logger.info(f"Found {len(campaigns)} active campaigns")

        for campaign in campaigns:
            try:
                for period_type in periods:
                    # Вычисляем даты периода
                    days = period_days[period_type]
                    period_end = today
                    period_start = today - timedelta(days=days - 1)

                    # Агрегируем данные
                    aggregated = aggregate_period_for_campaign(
                        session,
                        campaign.internal_id,
                        period_type,
                        period_start,
                        period_end
                    )

                    if aggregated is None:
                        # Нет данных за период - удаляем запись если есть
                        deleted = session.query(StatPeriod).filter(
                            StatPeriod.campaign_id == campaign.internal_id,
                            StatPeriod.period_type == period_type,
                            StatPeriod.period_start == period_start,
                            StatPeriod.period_end == period_end
                        ).delete()

                        if deleted > 0:
                            stats['records_deleted'] += deleted
                            logger.debug(f"Deleted stat_period for campaign {campaign.binom_id} ({period_type})")
                        continue

                    # Ищем существующую запись
                    existing = session.query(StatPeriod).filter(
                        StatPeriod.campaign_id == campaign.internal_id,
                        StatPeriod.period_type == period_type,
                        StatPeriod.period_start == period_start,
                        StatPeriod.period_end == period_end
                    ).first()

                    if existing:
                        # Обновляем существующую запись
                        for key, value in aggregated.items():
                            if key not in ['campaign_id', 'period_type', 'period_start', 'period_end']:
                                setattr(existing, key, value)
                        stats['records_updated'] += 1
                        logger.debug(f"Updated stat_period for campaign {campaign.binom_id} ({period_type})")
                    else:
                        # Создаем новую запись
                        new_record = StatPeriod(**aggregated)
                        session.add(new_record)
                        stats['records_created'] += 1
                        logger.debug(f"Created stat_period for campaign {campaign.binom_id} ({period_type})")

                stats['campaigns_processed'] += 1

                # Коммитим каждые 50 кампаний
                if stats['campaigns_processed'] % 50 == 0:
                    session.commit()
                    logger.info(f"Processed {stats['campaigns_processed']}/{len(campaigns)} campaigns")

            except Exception as e:
                error_msg = f"Error processing campaign {campaign.binom_id}: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)
                session.rollback()
                continue

        # Финальный коммит
        session.commit()

    stats['periods_processed'] = len(periods)

    logger.info("=" * 60)
    logger.info("Stat_periods recalculation completed")
    logger.info(f"Campaigns processed: {stats['campaigns_processed']}")
    logger.info(f"Records created:     {stats['records_created']}")
    logger.info(f"Records updated:     {stats['records_updated']}")
    logger.info(f"Records deleted:     {stats['records_deleted']}")
    logger.info(f"Errors:              {len(stats['errors'])}")
    logger.info("=" * 60)

    return stats


if __name__ == '__main__':
    # Настраиваем логирование для standalone запуска
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Запускаем пересчет
    result = recalculate_stat_periods()

    print("\n" + "=" * 60)
    print("RECALCULATION RESULTS")
    print("=" * 60)
    print(f"Periods processed:   {result['periods_processed']}")
    print(f"Campaigns processed: {result['campaigns_processed']}")
    print(f"Records created:     {result['records_created']}")
    print(f"Records updated:     {result['records_updated']}")
    print(f"Records deleted:     {result['records_deleted']}")

    if result['errors']:
        print(f"\nErrors: {len(result['errors'])}")
        for error in result['errors'][:10]:
            print(f"  - {error}")

    print("=" * 60)
