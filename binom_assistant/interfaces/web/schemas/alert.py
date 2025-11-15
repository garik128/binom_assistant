"""
Pydantic AE5<K 4;O 0;5@B>2.
"""
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime


class AlertResponse(BaseModel):
    """;5@B"""
    campaign_id: int
    campaign_name: str
    alert_type: str
    severity: str
    message: str
    created_at: datetime


class AlertsListResponse(BaseModel):
    """!?8A>: 0;5@B>2"""
    alerts: List[AlertResponse]
    total: int
    critical_count: int
    warning_count: int
    info_count: int


class AnomalyResponse(BaseModel):
    """=><0;8O"""
    campaign_id: int
    campaign_name: str
    anomaly_type: str
    metric: str
    old_value: float
    new_value: float
    change_percent: float
    severity: str
    description: str


class AnomaliesListResponse(BaseModel):
    """!?8A>: 0=><0;89"""
    anomalies: List[AnomalyResponse]
    total: int
