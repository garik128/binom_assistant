"""
Метаданные о модулях для маппинга категорий
"""

# Маппинг категорий на их модули
CATEGORY_MODULES = {
    "critical_alerts": [
        "bleeding_detector",
        "zero_approval_alert",
        "spend_spike_monitor",
        "waste_campaign_finder",
        "traffic_quality_crash",
        "squeezed_offer"
    ],
    "trend_analysis": [
        "microtrend_scanner",
        "momentum_tracker",
        "recovery_detector",
        "trend_reversal_finder",
        "acceleration_monitor"
    ],
    "stability": [
        "volatility_calculator",
        "consistency_scorer",
        "reliability_index",
        "performance_stability"
    ],
    "predictive": [
        "roi_forecast",
        "profitability_horizon",
        "approval_rate_predictor",
        "campaign_lifecycle_stage",
        "revenue_projection"
    ],
    "problem_detection": [
        "sleepy_campaign_finder",
        "cpl_margin_monitor",
        "conversion_drop_alert",
        "approval_delay_impact",
        "zombie_campaign_detector",
        "source_fatigue_detector"
    ],
    "opportunities": [
        "hidden_gems_finder",
        "sudden_winner_detector",
        "scaling_candidates",
        "breakout_alert"
    ],
    "segmentation": [
        "smart_consolidator",
        "performance_segmenter",
        "source_group_matrix"
    ],
    "portfolio": [
        "portfolio_health_index",
        "total_performance_tracker",
        "risk_assessment",
        "diversification_score",
        "budget_optimizer"
    ],
    "sources_offers": [
        "network_performance_monitor",
        "source_quality_scorer",
        "offer_profitability_ranker",
        "offer_lifecycle_tracker"
    ]
}


def get_modules_by_category(category_id: str) -> list:
    """
    Получает список модулей для категории

    Args:
        category_id: ID категории

    Returns:
        List модулей в категории
    """
    return CATEGORY_MODULES.get(category_id, [])


def get_all_modules() -> list:
    """
    Получает список всех модулей

    Returns:
        List всех модулей
    """
    all_modules = []
    for modules in CATEGORY_MODULES.values():
        all_modules.extend(modules)
    return all_modules
