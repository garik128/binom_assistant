# -*- coding: utf-8 -*-
"""
API endpoints для кампаний.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List
from ..dependencies import get_db
from ..auth import get_current_user
from ..schemas import (
    CampaignResponse,
    CampaignListResponse,
    CampaignDetailResponse
)
from storage.database.models import Campaign
import logging

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/campaigns", response_model=CampaignListResponse)
async def get_campaigns(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=200, description="Размер страницы"),
    group_name: Optional[str] = Query(None, description="Фильтр по группе"),
    ts_name: Optional[str] = Query(None, description="Фильтр по источнику"),
    is_cpl_mode: Optional[bool] = Query(None, description="Фильтр по типу (CPL/CPA)"),
    min_cost: Optional[float] = Query(None, description="Минимальный расход"),
    min_leads: Optional[int] = Query(None, description="Минимум лидов"),
    search: Optional[str] = Query(None, description="Поиск по имени"),
    db: Session = Depends(get_db)
):
    """
    Получить список кампаний с фильтрацией и пагинацией.

    Args:
        page: Номер страницы
        page_size: Количество элементов на странице
        group_name: Фильтр по группе
        ts_name: Фильтр по источнику
        is_cpl_mode: Фильтр по типу кампании
        min_cost: Минимальный расход
        min_leads: Минимум лидов
        search: Поиск по имени
        db: Сессия БД

    Returns:
        Список кампаний с пагинацией
    """
    try:
        # 07>2K9 70?@>A
        query = db.query(Campaign)

        # Применяем фильтры
        filters = []

        if group_name:
            filters.append(Campaign.group_name == group_name)

        if ts_name:
            filters.append(Campaign.ts_name == ts_name)

        if is_cpl_mode is not None:
            filters.append(Campaign.is_cpl_mode == is_cpl_mode)

        if min_cost is not None:
            filters.append(Campaign.cost >= min_cost)

        if min_leads is not None:
            filters.append(Campaign.leads >= min_leads)

        if search:
            filters.append(Campaign.current_name.ilike(f"%{search}%"))

        if filters:
            query = query.filter(and_(*filters))

        # Подсчет общего количества
        total = query.count()

        # 038=0F8O
        offset = (page - 1) * page_size
        campaigns = query.offset(offset).limit(page_size).all()

        # Вычисляем количество страниц
        pages = (total + page_size - 1) // page_size

        return CampaignListResponse(
            campaigns=[CampaignResponse.from_orm(c) for c in campaigns],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages
        )

    except Exception as e:
        logger.error(f"Error fetching campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/top")
async def get_top_campaigns(
    period: str = Query("7d", description="Период: 1d, yesterday, 7d, 14d, 30d, this_month, last_month"),
    limit: int = Query(5, ge=1, le=50, description="Количество кампаний"),
    sort_by: str = Query("roi", description="Поле для сортировки: roi, revenue, cost, profit, clicks, leads"),
    db: Session = Depends(get_db)
):
    """
    Получить топ кампаний по выбранному критерию за период.

    Args:
        period: Период для анализа
        limit: Количество кампаний
        sort_by: Поле для сортировки (roi, revenue, cost, profit, clicks, leads)
        db: Сессия БД

    Returns:
        Список топ кампаний
    """
    try:
        from storage.database.models import StatPeriod, CampaignStatsDaily
        from sqlalchemy import func
        from .utils import get_date_range_for_period, should_use_stat_period

        # Получаем диапазон дат для периода
        date_from, date_to = get_date_range_for_period(period)

        # Валидация sort_by
        valid_sort_fields = ['roi', 'revenue', 'cost', 'profit', 'clicks', 'leads']
        if sort_by not in valid_sort_fields:
            raise HTTPException(status_code=400, detail=f"Invalid sort_by value. Must be one of: {', '.join(valid_sort_fields)}")

        # Определяем источник данных
        if should_use_stat_period(period):
            # Для 7d, 14d, 30d используем StatPeriod
            period_mapping = {
                '7d': '7days',
                '14d': '14days',
                '30d': '30days'
            }
            period_type = period_mapping[period]

            # Подзапрос для получения максимального snapshot_time для каждой кампании
            from sqlalchemy.sql import func as sql_func

            latest_snapshot = db.query(
                StatPeriod.campaign_id,
                sql_func.max(StatPeriod.snapshot_time).label('max_snapshot')
            ).filter(
                StatPeriod.period_type == period_type
            ).group_by(StatPeriod.campaign_id).subquery()

            # Маппинг полей для сортировки
            sort_field_map = {
                'roi': StatPeriod.roi,
                'revenue': StatPeriod.revenue,
                'cost': StatPeriod.cost,
                'profit': (StatPeriod.revenue - StatPeriod.cost),
                'clicks': StatPeriod.clicks,
                'leads': StatPeriod.leads
            }
            sort_field = sort_field_map[sort_by]

            # Основной запрос с JOIN к подзапросу
            query = db.query(
                Campaign.internal_id,
                Campaign.current_name,
                Campaign.binom_id,
                StatPeriod.cost.label('total_cost'),
                StatPeriod.revenue.label('total_revenue'),
                StatPeriod.clicks.label('total_clicks'),
                StatPeriod.leads.label('total_leads'),
                StatPeriod.roi.label('roi')
            ).join(
                StatPeriod, Campaign.internal_id == StatPeriod.campaign_id
            ).join(
                latest_snapshot,
                and_(
                    StatPeriod.campaign_id == latest_snapshot.c.campaign_id,
                    StatPeriod.snapshot_time == latest_snapshot.c.max_snapshot
                )
            ).filter(
                StatPeriod.period_type == period_type
            )

            # Применяем сортировку
            top_campaigns = query.order_by(sort_field.desc()).limit(limit).all()
        else:
            # Для 1d, yesterday, this_month, last_month используем CampaignStatsDaily
            # Вычисляем агрегированные поля
            total_cost_expr = func.sum(CampaignStatsDaily.cost)
            total_revenue_expr = func.sum(CampaignStatsDaily.revenue)
            total_clicks_expr = func.sum(CampaignStatsDaily.clicks)
            total_leads_expr = func.sum(CampaignStatsDaily.leads)
            roi_expr = ((total_revenue_expr - total_cost_expr) / total_cost_expr * 100)
            profit_expr = (total_revenue_expr - total_cost_expr)

            # Маппинг полей для сортировки
            sort_field_map = {
                'roi': roi_expr,
                'revenue': total_revenue_expr,
                'cost': total_cost_expr,
                'profit': profit_expr,
                'clicks': total_clicks_expr,
                'leads': total_leads_expr
            }
            sort_field = sort_field_map[sort_by]

            # Агрегируем данные за период
            query = db.query(
                Campaign.internal_id,
                Campaign.current_name,
                Campaign.binom_id,
                total_cost_expr.label('total_cost'),
                total_revenue_expr.label('total_revenue'),
                total_clicks_expr.label('total_clicks'),
                total_leads_expr.label('total_leads'),
                roi_expr.label('roi')
            ).join(
                CampaignStatsDaily, Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.date <= date_to
            ).group_by(
                Campaign.internal_id,
                Campaign.current_name,
                Campaign.binom_id
            )

            # Применяем сортировку
            top_campaigns = query.order_by(sort_field.desc()).limit(limit).all()

        # Формируем результат
        campaigns = [
            {
                'id': campaign.internal_id,
                'name': campaign.current_name or f'Campaign #{campaign.binom_id}',
                'binom_id': campaign.binom_id,
                'cost': round(float(campaign.total_cost or 0), 2),
                'revenue': round(float(campaign.total_revenue or 0), 2),
                'clicks': int(campaign.total_clicks or 0),
                'leads': int(campaign.total_leads or 0),
                'roi': round(float(campaign.roi or 0), 2)
            }
            for campaign in top_campaigns
        ]

        return {
            'campaigns': campaigns,
            'total': len(campaigns),
            'period': period
        }

    except Exception as e:
        logger.error(f"Error fetching top campaigns: {e}")
        # Возвращаем пустой список вместо ошибки
        return {
            'campaigns': [],
            'total': 0,
            'period': period
        }


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailResponse)
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db)
):
    """
    Получить детальную информацию о кампании.

    Args:
        campaign_id: ID кампании
        db: Сессия БД

    Returns:
        Детальная информация о кампании
    """
    try:
        campaign = db.query(Campaign).filter(Campaign.internal_id == campaign_id).first()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        return CampaignDetailResponse.from_orm(campaign)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/by-group/{group_name}", response_model=CampaignListResponse)
async def get_campaigns_by_group(
    group_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Получить кампании определенной группы.

    Args:
        group_name: Название группы
        page: Номер страницы
        page_size: Размер страницы
        db: Сессия БД

    Returns:
        Список кампаний группы
    """
    return await get_campaigns(
        page=page,
        page_size=page_size,
        group_name=group_name,
        db=db
    )


@router.get("/campaigns/search/{query}", response_model=CampaignListResponse)
async def search_campaigns(
    query: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Поиск кампаний по названию.

    Args:
        query: Поисковый запрос
        page: Номер страницы
        page_size: Размер страницы
        db: Сессия БД

    Returns:
        Список найденных кампаний
    """
    return await get_campaigns(
        page=page,
        page_size=page_size,
        search=query,
        db=db
    )
