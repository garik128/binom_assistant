"""
Модули критических алертов
"""
from .bleeding_detector import BleedingCampaignDetector
from .zero_approval_alert import ZeroApprovalAlert
from .spend_spike_monitor import SpendSpikeMonitor
from .waste_campaign_finder import WasteCampaignFinder
from .traffic_quality_crash import TrafficQualityCrash
from .squeezed_offer import SqueezedOfferDetector

__all__ = [
    'BleedingCampaignDetector',
    'ZeroApprovalAlert',
    'SpendSpikeMonitor',
    'WasteCampaignFinder',
    'TrafficQualityCrash',
    'SqueezedOfferDetector'
]
