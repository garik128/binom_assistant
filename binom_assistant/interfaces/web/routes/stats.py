# -*- coding: utf-8 -*-
"""
API endpoints для статистики.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta
from ..dependencies import get_db
from ..auth import get_current_user
from ..schemas import (
    AggregatedStats,
    GroupStatsResponse,
    GroupStats,
    DailyStatsResponse,
    DailyStats
)
from storage.database.models import (
    Campaign, CampaignStatsDaily, StatPeriod,
    TrafficSource, TrafficSourceStatsDaily,
    Offer, OfferStatsDaily,
    AffiliateNetwork, NetworkStatsDaily
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# Импортируем вспомогательные функции для работы с периодами
from .utils import get_date_range_for_period


def validate_period_days(period: str) -> int:
    """
    Валидирует и парсит параметр периода вида '7d', '30d' и т.д.

    Args:
        period: Строка периода (например '7d')

    Returns:
        Количество дней

    Raises:
        HTTPException: Если формат неверный или значение вне допустимого диапазона
    """
    if not period.endswith('d'):
        raise HTTPException(
            status_code=400,
            detail="Invalid period format. Expected format: '7d', '30d', etc."
        )

    try:
        days = int(period[:-1])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid period format. Expected a number followed by 'd'"
        )

    if days < 1 or days > 365:
        raise HTTPException(
            status_code=400,
            detail="Period must be between 1 and 365 days"
        )

    return days


@router.get("/stats/overview", response_model=AggregatedStats)
async def get_overview_stats(
    period: str = Query("7d", description="Период: 1d, 7d, 14d, 30d"),
    db: Session = Depends(get_db)
):
    """
    Получить общую статистику за период.

    Args:
        period: Период (1d, 7d, 14d, 30d)
        db: Сессия БД

    Returns:
        Агрегированная статистика
    """
    try:
        # Парсим период
        days = validate_period_days(period)
        # Для "сегодня" берем с 00:00:00, для остальных - последние N дней
        if days == 1:
            date_from = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date_from = datetime.now() - timedelta(days=days - 1)

        # Получаем данные из StatDaily
        # Маппинг периодов на period_type в StatPeriod
        period_mapping = {
            '1d': 'today',
            '7d': '7days',
            '14d': '14days',
            '30d': '30days'
        }
        period_type = period_mapping.get(period, '7days')

        # Берем только самые свежие данные (с максимальной period_end для данного period_type)
        # Сначала находим максимальную period_end
        max_period_end = db.query(
            func.max(StatPeriod.period_end)
        ).filter(
            StatPeriod.period_type == period_type
        ).scalar()

        if not max_period_end:
            return AggregatedStats()

        stats_query = db.query(
            func.count(func.distinct(StatPeriod.campaign_id)).label('total_campaigns'),
            func.sum(StatPeriod.cost).label('total_cost'),
            func.sum(StatPeriod.revenue).label('total_revenue'),
            func.sum(StatPeriod.clicks).label('total_clicks'),
            func.sum(StatPeriod.leads).label('total_leads')
        ).filter(
            StatPeriod.period_type == period_type,
            StatPeriod.period_end == max_period_end  # Только самые свежие данные
        )

        result = stats_query.first()

        if not result or not result.total_campaigns:
            return AggregatedStats()

        total_cost = float(result.total_cost or 0)
        total_revenue = float(result.total_revenue or 0)
        total_profit = total_revenue - total_cost
        avg_roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

        total_clicks = int(result.total_clicks or 0)
        total_leads = int(result.total_leads or 0)
        avg_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0

        # Считаем активные кампании (с расходом > 1$ за период)
        active_campaigns = db.query(
            func.count(func.distinct(StatPeriod.campaign_id))
        ).filter(
            StatPeriod.period_type == period_type,
            StatPeriod.period_end == max_period_end,  # Только актуальные данные
            StatPeriod.cost > 1.0
        ).scalar() or 0

        return AggregatedStats(
            total_campaigns=result.total_campaigns,
            active_campaigns=active_campaigns,
            total_cost=total_cost,
            total_revenue=total_revenue,
            total_profit=total_profit,
            avg_roi=avg_roi,
            total_clicks=total_clicks,
            total_leads=total_leads,
            avg_cr=avg_cr
        )

    except Exception as e:
        logger.error(f"Error fetching overview stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/by-groups", response_model=GroupStatsResponse)
async def get_stats_by_groups(
    period: str = Query("7d", description="Период: 1d, 7d, 14d, 30d"),
    grouping: str = Query("group_name", description=">;5 3@C??8@>2:8"),
    db: Session = Depends(get_db)
):
    """
    Получить статистику по группам.

    Args:
        period: 5@8>4
        grouping: >;5 4;O 3@C??8@>2:8 (group_name, ts_name, domain_name)
        db: Сессия БД

    Returns:
        Статистика по группам
    """
    try:
        days = validate_period_days(period)
        # Для "сегодня" берем с 00:00:00, для остальных - последние N дней
        if days == 1:
            date_from = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date_from = datetime.now() - timedelta(days=days - 1)

        # ?@545;O5< ?>;5 4;O 3@C??8@>2:8
        group_field = getattr(Campaign, grouping, Campaign.group_name)

        # 3@538@C5< ?> 3@C??0<
        # Маппинг периодов
        period_mapping = {
            '1d': 'today',
            '7d': '7days',
            '14d': '14days',
            '30d': '30days'
        }
        period_type = period_mapping.get(period, '7days')

        # Берем только актуальные данные (period_end = сегодня)
        from datetime import date as dt_date
        today = dt_date.today()

        stats_query = db.query(
            group_field.label('group_name'),
            func.count(func.distinct(StatPeriod.campaign_id)).label('campaigns_count'),
            func.sum(StatPeriod.cost).label('total_cost'),
            func.sum(StatPeriod.revenue).label('total_revenue'),
            func.sum(StatPeriod.clicks).label('total_clicks'),
            func.sum(StatPeriod.leads).label('total_leads')
        ).join(
            Campaign, StatPeriod.campaign_id == Campaign.internal_id
        ).filter(
            StatPeriod.period_type == period_type,
            StatPeriod.period_end == today  # Только актуальные данные
        ).group_by(group_field).all()

        groups = []
        for row in stats_query:
            total_cost = float(row.total_cost or 0)
            total_revenue = float(row.total_revenue or 0)
            total_profit = total_revenue - total_cost
            avg_roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

            total_clicks = int(row.total_clicks or 0)
            total_leads = int(row.total_leads or 0)
            avg_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0

            groups.append(GroupStats(
                group_name=row.group_name or 'Unknown',
                campaigns_count=row.campaigns_count,
                total_cost=total_cost,
                total_revenue=total_revenue,
                total_profit=total_profit,
                avg_roi=avg_roi,
                total_leads=total_leads,
                avg_cr=avg_cr
            ))

        # !>@B8@C5< ?> @0AE>4C
        groups.sort(key=lambda x: x.total_cost, reverse=True)

        return GroupStatsResponse(
            groups=groups,
            total_groups=len(groups)
        )

    except Exception as e:
        logger.error(f"Error fetching group stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/campaign/{campaign_id}/daily", response_model=DailyStatsResponse)
async def get_campaign_daily_stats(
    campaign_id: int,
    days: int = Query(7, ge=1, le=90, description=">;8G5AB2> 4=59"),
    db: Session = Depends(get_db)
):
    """
    >;CG8BL 4=52=CN AB0B8AB8:C :0<?0=88.

    Args:
        campaign_id: ID кампании
        days: >;8G5AB2> 4=59 =0704
        db: Сессия БД

    Returns:
        =52=0O AB0B8AB8:0
    """
    try:
        # >;CG05< :0<?0=8N
        campaign = db.query(Campaign).filter(Campaign.internal_id == campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # >;CG05< 4=52=CN AB0B8AB8:C
        date_from = datetime.now() - timedelta(days=days - 1)

        daily_stats = db.query(CampaignStatsDaily).filter(
            CampaignStatsDaily.campaign_id == campaign_id,
            CampaignStatsDaily.date >= date_from.date()
        ).order_by(CampaignStatsDaily.date).all()

        stats = [
            DailyStats(
                date=stat.date,
                clicks=stat.clicks,
                leads=stat.leads,
                cost=stat.cost,
                revenue=stat.revenue,
                profit=stat.profit,
                roi=stat.roi,
                cr=stat.cr
            )
            for stat in daily_stats
        ]

        return DailyStatsResponse(
            campaign_id=campaign_id,
            campaign_name=campaign.current_name,
            stats=stats,
            period_start=date_from.date(),
            period_end=datetime.now().date()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching daily stats for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/charts")
async def get_charts_data(
    period: str = Query("7d", description="Период: 1d, yesterday, 7d, 14d, 30d, this_month, last_month"),
    db: Session = Depends(get_db)
):
    """
    Получить данные для графиков дашборда.

    Args:
        period: Период
        db: Сессия БД

    Returns:
        Данные для ROI по дням и распределения расходов
    """
    try:
        # Получаем диапазон дат для периода
        date_from, date_to = get_date_range_for_period(period)

        # Получаем данные трендов из БД (всегда из CampaignStatsDaily, группируем по датам)
        roi_query = db.query(
            CampaignStatsDaily.date,
            func.sum(CampaignStatsDaily.cost).label('total_cost'),
            func.sum(CampaignStatsDaily.revenue).label('total_revenue')
        ).filter(
            CampaignStatsDaily.date >= date_from,
            CampaignStatsDaily.date <= date_to
        ).group_by(
            CampaignStatsDaily.date
        ).order_by(
            CampaignStatsDaily.date.asc()
        ).all()

        roi_by_days = []
        for row in roi_query:
            cost = float(row.total_cost or 0)
            revenue = float(row.total_revenue or 0)
            profit = revenue - cost
            roi = (profit / cost * 100) if cost > 0 else 0

            roi_by_days.append({
                'date': row.date.isoformat(),
                'roi': round(roi, 2),
                'cost': round(cost, 2),
                'revenue': round(revenue, 2)
            })

        # Распределение расходов по топ-10 источникам трафика
        # Используем TrafficSourceStatsDaily для всех периодов
        top_sources_query = db.query(
            TrafficSource.name,
            func.sum(TrafficSourceStatsDaily.cost).label('cost')
        ).join(
            TrafficSource, TrafficSourceStatsDaily.ts_id == TrafficSource.id
        ).filter(
            TrafficSourceStatsDaily.date >= date_from,
            TrafficSourceStatsDaily.date <= date_to
        ).group_by(
            TrafficSourceStatsDaily.ts_id,
            TrafficSource.name
        ).order_by(
            func.sum(TrafficSourceStatsDaily.cost).desc()
        ).limit(10).all()

        spend_distribution = [
            {
                'name': row.name or 'Неизвестен',
                'cost': round(float(row.cost or 0), 2)
            }
            for row in top_sources_query
        ]

        # Распределение доходов по топ-10 партнерским сетям
        # Используем NetworkStatsDaily для всех периодов
        top_networks_query = db.query(
            AffiliateNetwork.name,
            func.sum(NetworkStatsDaily.revenue).label('revenue')
        ).join(
            AffiliateNetwork, NetworkStatsDaily.network_id == AffiliateNetwork.id
        ).filter(
            NetworkStatsDaily.date >= date_from,
            NetworkStatsDaily.date <= date_to
        ).group_by(
            NetworkStatsDaily.network_id,
            AffiliateNetwork.name
        ).order_by(
            func.sum(NetworkStatsDaily.revenue).desc()
        ).limit(10).all()

        revenue_distribution = [
            {
                'name': row.name or 'Неизвестна',
                'revenue': round(float(row.revenue or 0), 2)
            }
            for row in top_networks_query
        ]

        return {
            'roi_by_days': roi_by_days,
            'spend_distribution': spend_distribution,
            'revenue_distribution': revenue_distribution
        }

    except Exception as e:
        logger.error(f"Error fetching charts data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_summary_stats(
    period: str = Query("7d", description="Период: 1d, yesterday, 7d, 14d, 30d, this_month, last_month"),
    db: Session = Depends(get_db)
):
    """
    Получить сводную статистику для карточек дашборда.

    Args:
        period: Период
        db: Сессия БД

    Returns:
        Общая статистика
    """
    try:
        # Получаем диапазон дат для периода
        date_from, date_to = get_date_range_for_period(period)

        # Всегда используем CampaignStatsDaily для корректного подсчета уникальных кампаний по периодам
        # Подсчет кампаний - только те, у которых были клики (активные)
        active_campaigns_query = db.query(
            func.count(func.distinct(CampaignStatsDaily.campaign_id))
        ).filter(
            CampaignStatsDaily.date >= date_from,
            CampaignStatsDaily.date <= date_to,
            CampaignStatsDaily.clicks > 0  # Активная кампания = есть клики
        )
        campaigns_count = active_campaigns_query.scalar() or 0

        # Общая статистика (для всех метрик кроме количества кампаний)
        stats_query = db.query(
            func.sum(CampaignStatsDaily.cost).label('total_cost'),
            func.sum(CampaignStatsDaily.revenue).label('total_revenue'),
            func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
            func.sum(CampaignStatsDaily.leads).label('total_leads')
        ).filter(
            CampaignStatsDaily.date >= date_from,
            CampaignStatsDaily.date <= date_to
        )

        result = stats_query.first()

        if not result:
            return {
                'total_cost': 0,
                'total_revenue': 0,
                'roi': 0,
                'campaigns_count': campaigns_count
            }

        total_cost = float(result.total_cost or 0)
        total_revenue = float(result.total_revenue or 0)
        total_profit = total_revenue - total_cost
        roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

        return {
            'total_cost': round(total_cost, 2),
            'total_revenue': round(total_revenue, 2),
            'total_profit': round(total_profit, 2),
            'roi': round(roi, 2),
            'campaigns_count': campaigns_count
        }

    except Exception as e:
        logger.error(f"Error fetching summary stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    period: str = Query("7d", description="Период: 1d, yesterday, 7d, 14d, 30d, this_month, last_month"),
    db: Session = Depends(get_db)
):
    """
    Получить сводку для дашборда: топ источники, офферы, партнерки.

    Args:
        period: Период
        db: Сессия БД

    Returns:
        Сводная информация по источникам, офферам и партнеркам за период
    """
    try:
        # Получаем диапазон дат для периода
        date_from, date_to = get_date_range_for_period(period)

        # === ИСТОЧНИКИ ТРАФИКА ===
        ts_stats = db.query(
            TrafficSourceStatsDaily.ts_id,
            TrafficSource.name,
            func.sum(TrafficSourceStatsDaily.cost).label('total_cost'),
            func.sum(TrafficSourceStatsDaily.revenue).label('total_revenue')
        ).join(
            TrafficSource, TrafficSourceStatsDaily.ts_id == TrafficSource.id
        ).filter(
            TrafficSourceStatsDaily.date >= date_from,
            TrafficSourceStatsDaily.date <= date_to
        ).group_by(
            TrafficSourceStatsDaily.ts_id,
            TrafficSource.name
        ).all()

        # Вычисляем ROI и находим топ по профиту (revenue)
        ts_with_stats = []
        for row in ts_stats:
            cost = float(row.total_cost or 0)
            revenue = float(row.total_revenue or 0)
            if cost > 0:
                profit = revenue - cost
                roi = (profit / cost * 100)
                ts_with_stats.append({
                    'name': row.name,
                    'roi': roi,
                    'cost': cost,
                    'revenue': revenue
                })

        ts_with_stats.sort(key=lambda x: x['revenue'], reverse=True)
        top_ts = ts_with_stats[0] if ts_with_stats else None

        # === ОФФЕРЫ ===
        offer_stats = db.query(
            OfferStatsDaily.offer_id,
            Offer.name,
            func.sum(OfferStatsDaily.cost).label('total_cost'),
            func.sum(OfferStatsDaily.revenue).label('total_revenue')
        ).join(
            Offer, OfferStatsDaily.offer_id == Offer.id
        ).filter(
            OfferStatsDaily.date >= date_from,
            OfferStatsDaily.date <= date_to
        ).group_by(
            OfferStatsDaily.offer_id,
            Offer.name
        ).all()

        # Вычисляем ROI и находим топ по профиту (revenue)
        offers_with_stats = []
        for row in offer_stats:
            cost = float(row.total_cost or 0)
            revenue = float(row.total_revenue or 0)
            if cost > 0:
                profit = revenue - cost
                roi = (profit / cost * 100)
                offers_with_stats.append({
                    'name': row.name,
                    'roi': roi,
                    'cost': cost,
                    'revenue': revenue
                })

        offers_with_stats.sort(key=lambda x: x['revenue'], reverse=True)
        top_offer = offers_with_stats[0] if offers_with_stats else None

        # === ПАРТНЕРКИ ===
        network_stats = db.query(
            NetworkStatsDaily.network_id,
            AffiliateNetwork.name,
            func.sum(NetworkStatsDaily.cost).label('total_cost'),
            func.sum(NetworkStatsDaily.revenue).label('total_revenue')
        ).join(
            AffiliateNetwork, NetworkStatsDaily.network_id == AffiliateNetwork.id
        ).filter(
            NetworkStatsDaily.date >= date_from,
            NetworkStatsDaily.date <= date_to
        ).group_by(
            NetworkStatsDaily.network_id,
            AffiliateNetwork.name
        ).all()

        # Вычисляем ROI и находим топ по профиту (revenue)
        networks_with_stats = []
        for row in network_stats:
            cost = float(row.total_cost or 0)
            revenue = float(row.total_revenue or 0)
            if cost > 0:
                profit = revenue - cost
                roi = (profit / cost * 100)
                networks_with_stats.append({
                    'name': row.name,
                    'roi': roi,
                    'cost': cost,
                    'revenue': revenue
                })

        networks_with_stats.sort(key=lambda x: x['revenue'], reverse=True)
        top_network = networks_with_stats[0] if networks_with_stats else None

        return {
            'traffic_sources': {
                'count': len(ts_stats),
                'top': {
                    'name': top_ts['name'] if top_ts else None,
                    'roi': round(top_ts['roi'], 2) if top_ts else 0,
                    'revenue': round(top_ts['revenue'], 2) if top_ts else 0
                } if top_ts else None
            },
            'offers': {
                'count': len(offer_stats),
                'top': {
                    'name': top_offer['name'] if top_offer else None,
                    'roi': round(top_offer['roi'], 2) if top_offer else 0,
                    'revenue': round(top_offer['revenue'], 2) if top_offer else 0
                } if top_offer else None
            },
            'networks': {
                'count': len(network_stats),
                'top': {
                    'name': top_network['name'] if top_network else None,
                    'roi': round(top_network['roi'], 2) if top_network else 0,
                    'revenue': round(top_network['revenue'], 2) if top_network else 0
                } if top_network else None
            }
        }

    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/period-comparison")
async def get_period_comparison(
    period: str = Query("7d", description="Период: 1d, yesterday, 7d, 14d, 30d, this_month, last_month"),
    db: Session = Depends(get_db)
):
    """
    Сравнение текущего периода с предыдущим аналогичным периодом.

    Для momentum chart, delta chart и sparkline trends.

    Args:
        period: Период для сравнения
        db: Сессия БД

    Returns:
        Данные текущего и предыдущего периодов + процентные изменения
    """
    try:
        # Получаем диапазон дат для текущего периода
        current_from, current_to = get_date_range_for_period(period)

        # Вычисляем предыдущий период (того же размера)
        period_length = (current_to - current_from).days + 1
        previous_to = current_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_length - 1)

        # Функция для получения агрегированных данных за период
        def get_period_stats(date_from, date_to):
            stats = db.query(
                func.sum(CampaignStatsDaily.cost).label('cost'),
                func.sum(CampaignStatsDaily.revenue).label('revenue'),
                func.sum(CampaignStatsDaily.clicks).label('clicks'),
                func.sum(CampaignStatsDaily.leads).label('leads'),
                func.avg(CampaignStatsDaily.approve).label('approve_rate')
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.date <= date_to
            ).first()

            cost = float(stats.cost or 0)
            revenue = float(stats.revenue or 0)
            clicks = int(stats.clicks or 0)
            leads = int(stats.leads or 0)
            approve_rate = float(stats.approve_rate or 0)
            profit = revenue - cost
            roi = (profit / cost * 100) if cost > 0 else 0
            cr = (leads / clicks * 100) if clicks > 0 else 0

            return {
                'cost': round(cost, 2),
                'revenue': round(revenue, 2),
                'profit': round(profit, 2),
                'roi': round(roi, 2),
                'clicks': clicks,
                'leads': leads,
                'cr': round(cr, 2),
                'approve_rate': round(approve_rate, 2)
            }

        # Получаем данные за оба периода
        current_stats = get_period_stats(current_from, current_to)
        previous_stats = get_period_stats(previous_from, previous_to)

        # Вычисляем изменения (дельты)
        def calculate_delta(current, previous, is_percentage=False):
            """
            Вычисляет изменение между текущим и предыдущим значением.

            Для метрик-процентов (ROI, CR) используется разница в процентных пунктах.
            Для абсолютных метрик (revenue, cost) используется относительное изменение в процентах.
            """
            if is_percentage:
                # Для процентных метрик: просто разница в процентных пунктах
                # Например: 57.78% - 51.81% = +5.97 п.п.
                return round(current - previous, 2)
            else:
                # Для абсолютных метрик: относительное изменение в процентах
                # Например: (1500 - 1000) / 1000 * 100 = +50%
                if previous == 0:
                    return 100.0 if current > 0 else 0.0
                return round(((current - previous) / abs(previous)) * 100, 2)

        deltas = {
            'roi': calculate_delta(current_stats['roi'], previous_stats['roi'], is_percentage=True),
            'revenue': calculate_delta(current_stats['revenue'], previous_stats['revenue'], is_percentage=False),
            'profit': calculate_delta(current_stats['profit'], previous_stats['profit'], is_percentage=False),
            'clicks': calculate_delta(current_stats['clicks'], previous_stats['clicks'], is_percentage=False),
            'cr': calculate_delta(current_stats['cr'], previous_stats['cr'], is_percentage=True),
            'cost': calculate_delta(current_stats['cost'], previous_stats['cost'], is_percentage=False),
            'approve_rate': calculate_delta(current_stats['approve_rate'], previous_stats['approve_rate'], is_percentage=True)
        }

        # Получаем daily данные для sparklines (последние 14 точек текущего периода)
        daily_data = db.query(
            CampaignStatsDaily.date,
            func.sum(CampaignStatsDaily.cost).label('cost'),
            func.sum(CampaignStatsDaily.revenue).label('revenue'),
            func.sum(CampaignStatsDaily.clicks).label('clicks'),
            func.sum(CampaignStatsDaily.leads).label('leads'),
            func.count(func.distinct(CampaignStatsDaily.campaign_id)).label('campaigns')
        ).filter(
            CampaignStatsDaily.date >= current_from,
            CampaignStatsDaily.date <= current_to
        ).group_by(
            CampaignStatsDaily.date
        ).order_by(
            CampaignStatsDaily.date
        ).all()

        sparkline_data = []
        for row in daily_data:
            cost = float(row.cost or 0)
            revenue = float(row.revenue or 0)
            clicks = int(row.clicks or 0)
            leads = int(row.leads or 0)
            campaigns = int(row.campaigns or 0)
            profit = revenue - cost
            roi = (profit / cost * 100) if cost > 0 else 0
            cr = (leads / clicks * 100) if clicks > 0 else 0

            sparkline_data.append({
                'date': row.date.isoformat(),
                'roi': round(roi, 2),
                'revenue': round(revenue, 2),
                'profit': round(profit, 2),
                'clicks': clicks,
                'leads': leads,
                'campaigns': campaigns,
                'cr': round(cr, 2)
            })

        return {
            'current': current_stats,
            'previous': previous_stats,
            'deltas': deltas,
            'sparklines': sparkline_data,
            'period_info': {
                'current_from': current_from.isoformat(),
                'current_to': current_to.isoformat(),
                'previous_from': previous_from.isoformat(),
                'previous_to': previous_to.isoformat(),
                'period_length': period_length
            }
        }

    except Exception as e:
        logger.error(f"Error fetching period comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
