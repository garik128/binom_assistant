"""
Pydantic AE5<K 4;O :0<?0=89.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CampaignBase(BaseModel):
    """07>20O AE5<0 :0<?0=88"""
    id: int = Field(alias='binom_id')
    name: str = Field(alias='current_name')
    group_name: Optional[str] = None
    ts_name: Optional[str] = None
    domain_name: Optional[str] = None
    is_cpl_mode: bool = False
    is_active: Optional[bool] = True
    status: Optional[str] = 'active'


class CampaignStats(BaseModel):
    """!B0B8AB8:0 :0<?0=88"""
    clicks: int = 0
    leads: int = 0
    cost: float = 0.0
    revenue: float = 0.0
    profit: float = 0.0
    roi: float = 0.0
    cr: float = 0.0
    cpc: float = 0.0
    approve: float = 0.0
    a_leads: int = 0
    h_leads: int = 0
    r_leads: int = 0


class CampaignResponse(CampaignBase, CampaignStats):
    """>;=K9 >B25B A 40==K<8 :0<?0=88"""

    class Config:
        from_attributes = True
        populate_by_name = True


class CampaignListResponse(BaseModel):
    """!?8A>: :0<?0=89 A ?038=0F859"""
    campaigns: List[CampaignResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CampaignDetailResponse(CampaignResponse):
    """5B0;L=0O 8=D>@<0F8O > :0<?0=88"""
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class CampaignFilter(BaseModel):
    """$8;LB@K 4;O A?8A:0 :0<?0=89"""
    group_name: Optional[str] = None
    ts_name: Optional[str] = None
    domain_name: Optional[str] = None
    is_cpl_mode: Optional[bool] = None
    min_cost: Optional[float] = None
    min_leads: Optional[int] = None
    min_roi: Optional[float] = None
    max_roi: Optional[float] = None
