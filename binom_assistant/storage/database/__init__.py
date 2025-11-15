"""
Модуль для работы с базой данных
"""
from .base import (
    Base,
    get_engine,
    get_session_factory,
    get_session,
    session_scope,
    create_tables,
    drop_tables
)
from .models import (
    Campaign,
    CampaignStatsDaily,
    StatPeriod,
    StatWeekly,
    Alert,
    NameChange,
    SystemCache,
    TrafficSource,
    TrafficSourceStatsDaily,
    Offer,
    OfferStatsDaily,
    AffiliateNetwork,
    NetworkStatsDaily,
    ModuleConfig,
    ModuleRun,
    ModuleCache,
    BackgroundTask,
    AppSettings
)

# Алиасы для обратной совместимости
StatDaily = CampaignStatsDaily
from .migrate import (
    upgrade as migrate_upgrade,
    downgrade as migrate_downgrade,
    current as migrate_current,
    history as migrate_history
)

__all__ = [
    # Base
    'Base',
    'get_engine',
    'get_session_factory',
    'get_session',
    'session_scope',
    'create_tables',
    'drop_tables',
    # Models
    'Campaign',
    'CampaignStatsDaily',
    'StatDaily',  # Alias для CampaignStatsDaily
    'StatPeriod',
    'StatWeekly',
    'Alert',
    'NameChange',
    'SystemCache',
    'TrafficSource',
    'TrafficSourceStatsDaily',
    'Offer',
    'OfferStatsDaily',
    'AffiliateNetwork',
    'NetworkStatsDaily',
    'ModuleConfig',
    'ModuleRun',
    'ModuleCache',
    'BackgroundTask',
    'AppSettings',
    # Migrations
    'migrate_upgrade',
    'migrate_downgrade',
    'migrate_current',
    'migrate_history',
]
