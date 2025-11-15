"""
Pydantic AE5<K 4;O AB0B8AB8:8.
"""
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import date


class AggregatedStats(BaseModel):
    """3@538@>20==0O AB0B8AB8:0"""
    total_campaigns: int = 0
    active_campaigns: int = 0
    total_cost: float = 0.0
    total_revenue: float = 0.0
    total_profit: float = 0.0
    avg_roi: float = 0.0
    total_clicks: int = 0
    total_leads: int = 0
    avg_cr: float = 0.0


class GroupStats(BaseModel):
    """!B0B8AB8:0 ?> 3@C??5"""
    group_name: str
    campaigns_count: int
    total_cost: float
    total_revenue: float
    total_profit: float
    avg_roi: float
    total_leads: int
    avg_cr: float


class GroupStatsResponse(BaseModel):
    """B25B A> AB0B8AB8:>9 ?> 3@C??0<"""
    groups: List[GroupStats]
    total_groups: int


class DailyStats(BaseModel):
    """=52=0O AB0B8AB8:0"""
    date: date
    clicks: int = 0
    leads: int = 0
    cost: float = 0.0
    revenue: float = 0.0
    profit: float = 0.0
    roi: float = 0.0
    cr: float = 0.0


class DailyStatsResponse(BaseModel):
    """B25B A 4=52=>9 AB0B8AB8:>9"""
    campaign_id: int
    campaign_name: str
    stats: List[DailyStats]
    period_start: date
    period_end: date


class PeriodStats(BaseModel):
    """!B0B8AB8:0 70 ?5@8>4"""
    period_name: str
    stats: AggregatedStats


class ComparisonResponse(BaseModel):
    """!@02=5=85 42CE ?5@8>4>2"""
    period1: PeriodStats
    period2: PeriodStats
    changes: Dict[str, float]  # @>F5=B=K5 87<5=5=8O
