"""
DB Tools для AI агентов

Инструменты для прямого доступа к БД (read-only).
Используются агентами для получения raw данных когда аналитических модулей недостаточно.

ВАЖНО: Агенты НЕ имеют доступа к Binom API напрямую!
Только к локальной БД через эти tools.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
from sqlalchemy import desc, and_, or_, func
from sqlalchemy.orm import Session
import logging

from storage.database.base import get_session
from storage.database.models import (
    Campaign, CampaignStatsDaily, StatPeriod,
    TrafficSource, TrafficSourceStatsDaily,
    AffiliateNetwork, NetworkStatsDaily,
    Offer, OfferStatsDaily
)

logger = logging.getLogger(__name__)

# Лимиты для защиты от перегрузки контекста
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_DAYS_RANGE = 90


def validate_limit(limit: Optional[int]) -> int:
    """
    Валидирует и нормализует лимит записей.

    Args:
        limit: Запрошенный лимит

    Returns:
        int: Валидный лимит в пределах MIN-MAX
    """
    if limit is None:
        return DEFAULT_LIMIT

    if limit < 1:
        logger.warning(f"Limit {limit} < 1, using 1")
        return 1

    if limit > MAX_LIMIT:
        logger.warning(f"Limit {limit} > MAX_LIMIT ({MAX_LIMIT}), capping at MAX_LIMIT")
        return MAX_LIMIT

    return limit


def validate_date_range(date_from: Optional[str], date_to: Optional[str]) -> tuple:
    """
    Валидирует диапазон дат.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)

    Returns:
        tuple: (date_from_obj, date_to_obj) или (None, None) при ошибке
    """
    if not date_from and not date_to:
        return None, None

    try:
        df = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
        dt = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None

        # Проверка диапазона
        if df and dt:
            delta = (dt - df).days
            if delta < 0:
                logger.warning(f"date_from ({df}) > date_to ({dt}), swapping")
                df, dt = dt, df
                delta = abs(delta)

            if delta > MAX_DAYS_RANGE:
                logger.warning(f"Date range {delta} days > MAX ({MAX_DAYS_RANGE}), capping")
                dt = df + timedelta(days=MAX_DAYS_RANGE)

        return df, dt
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return None, None


def get_campaigns_list(
    limit: Optional[int] = None,
    is_active: Optional[bool] = None,
    is_cpl_mode: Optional[bool] = None,
    group_name: Optional[str] = None,
    search_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получает список кампаний из БД с фильтрацией.

    Args:
        limit: Максимальное количество записей (по умолчанию 100, макс 500)
        is_active: Фильтр по активности (True/False/None=все)
        is_cpl_mode: Фильтр по типу оплаты (True=CPL, False=CPA, None=все)
        group_name: Фильтр по группе (точное совпадение)
        search_name: Поиск по имени кампании (частичное совпадение, LIKE)

    Returns:
        Dict с полями:
        - campaigns: List[Dict] - список кампаний
        - total_returned: int - количество возвращенных записей
        - limit_applied: int - примененный лимит
    """
    limit = validate_limit(limit)

    session_gen = get_session()
    session = next(session_gen)

    try:
        query = session.query(Campaign)

        # Фильтры
        if is_active is not None:
            query = query.filter(Campaign.is_active == is_active)

        if is_cpl_mode is not None:
            query = query.filter(Campaign.is_cpl_mode == is_cpl_mode)

        if group_name:
            query = query.filter(Campaign.group_name == group_name)

        if search_name:
            query = query.filter(Campaign.current_name.like(f'%{search_name}%'))

        # Сортировка: сначала активные, потом по дате последнего обновления
        query = query.order_by(
            desc(Campaign.is_active),
            desc(Campaign.last_seen)
        )

        # Лимит
        query = query.limit(limit)

        campaigns = query.all()

        result = {
            'campaigns': [c.to_dict() for c in campaigns],
            'total_returned': len(campaigns),
            'limit_applied': limit
        }

        logger.info(f"get_campaigns_list: returned {len(campaigns)} campaigns (limit={limit})")
        return result

    except Exception as e:
        logger.error(f"Error in get_campaigns_list: {e}", exc_info=True)
        return {
            'error': str(e),
            'campaigns': [],
            'total_returned': 0,
            'limit_applied': limit
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def get_campaign_daily_stats(
    campaign_id: Optional[int] = None,
    binom_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    min_cost: Optional[float] = None,
    min_clicks: Optional[int] = None
) -> Dict[str, Any]:
    """
    Получает дневную статистику кампании.

    Args:
        campaign_id: Внутренний ID кампании (internal_id)
        binom_id: ID кампании в Binom
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
        limit: Максимальное количество записей
        min_cost: Минимальный расход (фильтр шума)
        min_clicks: Минимальное количество кликов (фильтр шума)

    Returns:
        Dict с полями:
        - stats: List[Dict] - дневная статистика
        - total_returned: int
        - limit_applied: int
    """
    if not campaign_id and not binom_id:
        return {
            'error': 'Either campaign_id or binom_id must be provided',
            'stats': [],
            'total_returned': 0
        }

    limit = validate_limit(limit)
    df, dt = validate_date_range(date_from, date_to)

    session_gen = get_session()
    session = next(session_gen)

    try:
        # Сначала находим campaign_id если передан binom_id
        if binom_id and not campaign_id:
            campaign = session.query(Campaign).filter(Campaign.binom_id == binom_id).first()
            if not campaign:
                return {
                    'error': f'Campaign with binom_id={binom_id} not found',
                    'stats': [],
                    'total_returned': 0
                }
            campaign_id = campaign.internal_id

        query = session.query(CampaignStatsDaily).filter(
            CampaignStatsDaily.campaign_id == campaign_id
        )

        # Фильтры по дате
        if df:
            query = query.filter(CampaignStatsDaily.date >= df)
        if dt:
            query = query.filter(CampaignStatsDaily.date <= dt)

        # Фильтры шума
        if min_cost is not None:
            query = query.filter(CampaignStatsDaily.cost >= min_cost)
        if min_clicks is not None:
            query = query.filter(CampaignStatsDaily.clicks >= min_clicks)

        # Сортировка по дате (новые сначала)
        query = query.order_by(desc(CampaignStatsDaily.date))

        # Лимит
        query = query.limit(limit)

        stats = query.all()

        result = {
            'stats': [s.to_dict() for s in stats],
            'total_returned': len(stats),
            'limit_applied': limit,
            'campaign_id': campaign_id
        }

        logger.info(f"get_campaign_daily_stats: campaign_id={campaign_id}, returned {len(stats)} records")
        return result

    except Exception as e:
        logger.error(f"Error in get_campaign_daily_stats: {e}", exc_info=True)
        return {
            'error': str(e),
            'stats': [],
            'total_returned': 0
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def get_campaigns_stats_aggregated(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    min_cost: Optional[float] = None,
    is_cpl_mode: Optional[bool] = None,
    group_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получает агрегированную статистику по кампаниям за период.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
        limit: Максимальное количество кампаний
        min_cost: Минимальный расход за период
        is_cpl_mode: Фильтр по типу оплаты
        group_name: Фильтр по группе

    Returns:
        Dict с агрегированной статистикой по кампаниям
    """
    limit = validate_limit(limit)
    df, dt = validate_date_range(date_from, date_to)

    # Если даты не указаны - последние 7 дней
    if not df:
        dt = date.today()
        df = dt - timedelta(days=7)

    session_gen = get_session()
    session = next(session_gen)

    try:
        # Агрегация: JOIN campaigns + SUM статистики за период
        query = session.query(
            Campaign.internal_id,
            Campaign.binom_id,
            Campaign.current_name,
            Campaign.group_name,
            Campaign.is_cpl_mode,
            func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
            func.sum(CampaignStatsDaily.leads).label('total_leads'),
            func.sum(CampaignStatsDaily.cost).label('total_cost'),
            func.sum(CampaignStatsDaily.revenue).label('total_revenue'),
            func.sum(CampaignStatsDaily.a_leads).label('total_a_leads'),
            func.sum(CampaignStatsDaily.h_leads).label('total_h_leads'),
            func.sum(CampaignStatsDaily.r_leads).label('total_r_leads'),
            func.avg(CampaignStatsDaily.roi).label('avg_roi'),
            func.avg(CampaignStatsDaily.cr).label('avg_cr'),
        ).join(
            CampaignStatsDaily,
            Campaign.internal_id == CampaignStatsDaily.campaign_id
        ).filter(
            CampaignStatsDaily.date >= df,
            CampaignStatsDaily.date <= dt
        )

        # Фильтры по кампаниям
        if is_cpl_mode is not None:
            query = query.filter(Campaign.is_cpl_mode == is_cpl_mode)

        if group_name:
            query = query.filter(Campaign.group_name == group_name)

        # Группировка
        query = query.group_by(Campaign.internal_id)

        # Фильтр по минимальному расходу (HAVING после GROUP BY)
        if min_cost:
            query = query.having(func.sum(CampaignStatsDaily.cost) >= min_cost)

        # Сортировка по расходу (большие первые)
        query = query.order_by(desc('total_cost'))

        # Лимит
        query = query.limit(limit)

        results = query.all()

        campaigns_stats = []
        for r in results:
            # Вычисляем ROI и profit
            profit = float(r.total_revenue or 0) - float(r.total_cost or 0)
            roi = (profit / float(r.total_cost) * 100) if r.total_cost and r.total_cost > 0 else None

            campaigns_stats.append({
                'internal_id': r.internal_id,
                'binom_id': r.binom_id,
                'current_name': r.current_name,
                'group_name': r.group_name,
                'is_cpl_mode': r.is_cpl_mode,
                'total_clicks': r.total_clicks or 0,
                'total_leads': r.total_leads or 0,
                'total_cost': float(r.total_cost or 0),
                'total_revenue': float(r.total_revenue or 0),
                'profit': profit,
                'roi': roi,
                'total_a_leads': r.total_a_leads or 0,
                'total_h_leads': r.total_h_leads or 0,
                'total_r_leads': r.total_r_leads or 0,
                'avg_roi': float(r.avg_roi) if r.avg_roi else None,
                'avg_cr': float(r.avg_cr) if r.avg_cr else None,
            })

        result = {
            'campaigns': campaigns_stats,
            'total_returned': len(campaigns_stats),
            'limit_applied': limit,
            'period': {
                'date_from': df.isoformat(),
                'date_to': dt.isoformat()
            }
        }

        logger.info(f"get_campaigns_stats_aggregated: {df} to {dt}, returned {len(campaigns_stats)} campaigns")
        return result

    except Exception as e:
        logger.error(f"Error in get_campaigns_stats_aggregated: {e}", exc_info=True)
        return {
            'error': str(e),
            'campaigns': [],
            'total_returned': 0
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def get_traffic_sources_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    min_cost: Optional[float] = None
) -> Dict[str, Any]:
    """
    Получает агрегированную статистику по источникам трафика.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
        limit: Максимальное количество источников
        min_cost: Минимальный расход за период

    Returns:
        Dict со статистикой по источникам
    """
    limit = validate_limit(limit)
    df, dt = validate_date_range(date_from, date_to)

    # Если даты не указаны - последние 7 дней
    if not df:
        dt = date.today()
        df = dt - timedelta(days=7)

    session_gen = get_session()
    session = next(session_gen)

    try:
        query = session.query(
            TrafficSource.id,
            TrafficSource.name,
            TrafficSource.status,
            func.sum(TrafficSourceStatsDaily.clicks).label('total_clicks'),
            func.sum(TrafficSourceStatsDaily.cost).label('total_cost'),
            func.sum(TrafficSourceStatsDaily.leads).label('total_leads'),
            func.sum(TrafficSourceStatsDaily.revenue).label('total_revenue'),
            func.sum(TrafficSourceStatsDaily.a_leads).label('total_a_leads'),
            func.avg(TrafficSourceStatsDaily.roi).label('avg_roi'),
            func.avg(TrafficSourceStatsDaily.cr).label('avg_cr'),
        ).join(
            TrafficSourceStatsDaily,
            TrafficSource.id == TrafficSourceStatsDaily.ts_id
        ).filter(
            TrafficSourceStatsDaily.date >= df,
            TrafficSourceStatsDaily.date <= dt
        )

        query = query.group_by(TrafficSource.id)

        if min_cost:
            query = query.having(func.sum(TrafficSourceStatsDaily.cost) >= min_cost)

        query = query.order_by(desc('total_cost'))
        query = query.limit(limit)

        results = query.all()

        sources_stats = []
        for r in results:
            profit = float(r.total_revenue or 0) - float(r.total_cost or 0)
            roi = (profit / float(r.total_cost) * 100) if r.total_cost and r.total_cost > 0 else None

            sources_stats.append({
                'ts_id': r.id,
                'ts_name': r.name,
                'status': r.status,
                'total_clicks': r.total_clicks or 0,
                'total_cost': float(r.total_cost or 0),
                'total_leads': r.total_leads or 0,
                'total_revenue': float(r.total_revenue or 0),
                'profit': profit,
                'roi': roi,
                'total_a_leads': r.total_a_leads or 0,
                'avg_roi': float(r.avg_roi) if r.avg_roi else None,
                'avg_cr': float(r.avg_cr) if r.avg_cr else None,
            })

        result = {
            'traffic_sources': sources_stats,
            'total_returned': len(sources_stats),
            'limit_applied': limit,
            'period': {
                'date_from': df.isoformat(),
                'date_to': dt.isoformat()
            }
        }

        logger.info(f"get_traffic_sources_stats: {df} to {dt}, returned {len(sources_stats)} sources")
        return result

    except Exception as e:
        logger.error(f"Error in get_traffic_sources_stats: {e}", exc_info=True)
        return {
            'error': str(e),
            'traffic_sources': [],
            'total_returned': 0
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def get_affiliate_networks_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    min_revenue: Optional[float] = None
) -> Dict[str, Any]:
    """
    Получает агрегированную статистику по партнерским сетям.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
        limit: Максимальное количество сетей
        min_revenue: Минимальный доход за период

    Returns:
        Dict со статистикой по партнерским сетям
    """
    limit = validate_limit(limit)
    df, dt = validate_date_range(date_from, date_to)

    if not df:
        dt = date.today()
        df = dt - timedelta(days=7)

    session_gen = get_session()
    session = next(session_gen)

    try:
        query = session.query(
            AffiliateNetwork.id,
            AffiliateNetwork.name,
            AffiliateNetwork.status,
            func.sum(NetworkStatsDaily.clicks).label('total_clicks'),
            func.sum(NetworkStatsDaily.leads).label('total_leads'),
            func.sum(NetworkStatsDaily.revenue).label('total_revenue'),
            func.sum(NetworkStatsDaily.cost).label('total_cost'),
            func.sum(NetworkStatsDaily.a_leads).label('total_a_leads'),
            func.sum(NetworkStatsDaily.h_leads).label('total_h_leads'),
            func.sum(NetworkStatsDaily.r_leads).label('total_r_leads'),
            func.avg(NetworkStatsDaily.approve).label('avg_approve'),
            func.avg(NetworkStatsDaily.roi).label('avg_roi'),
        ).join(
            NetworkStatsDaily,
            AffiliateNetwork.id == NetworkStatsDaily.network_id
        ).filter(
            NetworkStatsDaily.date >= df,
            NetworkStatsDaily.date <= dt
        )

        query = query.group_by(AffiliateNetwork.id)

        if min_revenue:
            query = query.having(func.sum(NetworkStatsDaily.revenue) >= min_revenue)

        query = query.order_by(desc('total_revenue'))
        query = query.limit(limit)

        results = query.all()

        networks_stats = []
        for r in results:
            profit = float(r.total_revenue or 0) - float(r.total_cost or 0)

            # Вычисляем approve rate
            total_leads_all = (r.total_a_leads or 0) + (r.total_h_leads or 0) + (r.total_r_leads or 0)
            approve_rate = (r.total_a_leads / total_leads_all * 100) if total_leads_all > 0 else None

            networks_stats.append({
                'network_id': r.id,
                'network_name': r.name,
                'status': r.status,
                'total_clicks': r.total_clicks or 0,
                'total_leads': r.total_leads or 0,
                'total_revenue': float(r.total_revenue or 0),
                'total_cost': float(r.total_cost or 0),
                'profit': profit,
                'total_a_leads': r.total_a_leads or 0,
                'total_h_leads': r.total_h_leads or 0,
                'total_r_leads': r.total_r_leads or 0,
                'approve_rate': approve_rate,
                'avg_approve': float(r.avg_approve) if r.avg_approve else None,
                'avg_roi': float(r.avg_roi) if r.avg_roi else None,
            })

        result = {
            'affiliate_networks': networks_stats,
            'total_returned': len(networks_stats),
            'limit_applied': limit,
            'period': {
                'date_from': df.isoformat(),
                'date_to': dt.isoformat()
            }
        }

        logger.info(f"get_affiliate_networks_stats: {df} to {dt}, returned {len(networks_stats)} networks")
        return result

    except Exception as e:
        logger.error(f"Error in get_affiliate_networks_stats: {e}", exc_info=True)
        return {
            'error': str(e),
            'affiliate_networks': [],
            'total_returned': 0
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def get_offers_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: Optional[int] = None,
    min_revenue: Optional[float] = None,
    network_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Получает агрегированную статистику по офферам.

    Args:
        date_from: Дата начала (YYYY-MM-DD)
        date_to: Дата окончания (YYYY-MM-DD)
        limit: Максимальное количество офферов
        min_revenue: Минимальный доход за период
        network_id: Фильтр по партнерской сети

    Returns:
        Dict со статистикой по офферам
    """
    limit = validate_limit(limit)
    df, dt = validate_date_range(date_from, date_to)

    if not df:
        dt = date.today()
        df = dt - timedelta(days=7)

    session_gen = get_session()
    session = next(session_gen)

    try:
        query = session.query(
            Offer.id,
            Offer.name,
            Offer.network_id,
            Offer.geo,
            Offer.payout,
            Offer.status,
            func.sum(OfferStatsDaily.clicks).label('total_clicks'),
            func.sum(OfferStatsDaily.leads).label('total_leads'),
            func.sum(OfferStatsDaily.revenue).label('total_revenue'),
            func.sum(OfferStatsDaily.cost).label('total_cost'),
            func.sum(OfferStatsDaily.a_leads).label('total_a_leads'),
            func.avg(OfferStatsDaily.cr).label('avg_cr'),
            func.avg(OfferStatsDaily.approve).label('avg_approve'),
            func.avg(OfferStatsDaily.roi).label('avg_roi'),
        ).join(
            OfferStatsDaily,
            Offer.id == OfferStatsDaily.offer_id
        ).filter(
            OfferStatsDaily.date >= df,
            OfferStatsDaily.date <= dt
        )

        # Фильтр по сети
        if network_id:
            query = query.filter(Offer.network_id == network_id)

        query = query.group_by(Offer.id)

        if min_revenue:
            query = query.having(func.sum(OfferStatsDaily.revenue) >= min_revenue)

        query = query.order_by(desc('total_revenue'))
        query = query.limit(limit)

        results = query.all()

        offers_stats = []
        for r in results:
            profit = float(r.total_revenue or 0) - float(r.total_cost or 0)

            offers_stats.append({
                'offer_id': r.id,
                'offer_name': r.name,
                'network_id': r.network_id,
                'geo': r.geo,
                'payout': float(r.payout) if r.payout else None,
                'status': r.status,
                'total_clicks': r.total_clicks or 0,
                'total_leads': r.total_leads or 0,
                'total_revenue': float(r.total_revenue or 0),
                'total_cost': float(r.total_cost or 0),
                'profit': profit,
                'total_a_leads': r.total_a_leads or 0,
                'avg_cr': float(r.avg_cr) if r.avg_cr else None,
                'avg_approve': float(r.avg_approve) if r.avg_approve else None,
                'avg_roi': float(r.avg_roi) if r.avg_roi else None,
            })

        result = {
            'offers': offers_stats,
            'total_returned': len(offers_stats),
            'limit_applied': limit,
            'period': {
                'date_from': df.isoformat(),
                'date_to': dt.isoformat()
            }
        }

        logger.info(f"get_offers_stats: {df} to {dt}, returned {len(offers_stats)} offers")
        return result

    except Exception as e:
        logger.error(f"Error in get_offers_stats: {e}", exc_info=True)
        return {
            'error': str(e),
            'offers': [],
            'total_returned': 0
        }
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass
