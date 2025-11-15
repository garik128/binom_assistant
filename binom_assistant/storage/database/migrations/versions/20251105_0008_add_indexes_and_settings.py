"""
Миграция 0008: Добавление индексов и дополнительных настроек

Добавляет:
- Индексы для поиска по названиям и датам кампаний
- Индексы для фильтрации шума в статистике
- Индексы на snapshot_time для всех таблиц со статистикой
- Дополнительные настройки хранения данных

Дата: 2025-11-05
"""
from alembic import op
import sqlalchemy as sa


# Ревизии
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    """Добавление индексов и настроек"""

    # === ИНДЕКСЫ ДЛЯ CAMPAIGNS ===
    # Индекс для поиска по имени кампании
    op.create_index('idx_campaigns_name', 'campaigns', ['current_name'])

    # Индекс для фильтрации по последнему обновлению
    op.create_index('idx_campaigns_last_seen', 'campaigns', [sa.text('last_seen DESC')])

    # Индекс для сортировки по дате создания
    op.create_index('idx_campaigns_created_at', 'campaigns', [sa.text('created_at DESC')])

    # Композитный частичный индекс для активных кампаний + группа
    # SQLite поддерживает WHERE в CREATE INDEX
    op.execute("""
        CREATE INDEX idx_campaigns_active_group ON campaigns(is_active, group_name)
        WHERE is_active = TRUE
    """)

    # === ИНДЕКСЫ ДЛЯ CAMPAIGN_STATS_DAILY (фильтрация шума) ===
    # Композитный индекс для фильтрации шума
    op.create_index('idx_stats_daily_cost_clicks', 'campaign_stats_daily',
                    ['cost', 'clicks', 'campaign_id', 'date'])

    # Частичный индекс для активных кампаний (проходящих фильтр шума)
    op.execute("""
        CREATE INDEX idx_stats_daily_active_campaigns
        ON campaign_stats_daily(campaign_id, date, cost, clicks)
        WHERE cost >= 1.0 AND clicks >= 50
    """)

    # === ИНДЕКСЫ НА SNAPSHOT_TIME ===
    # Для campaign_stats_daily
    op.create_index('idx_campaign_stats_snapshot', 'campaign_stats_daily', ['snapshot_time'])

    # Для stats_period (если существует)
    # Проверяем наличие таблицы через try/except
    try:
        op.create_index('idx_stats_period_snapshot', 'stats_period', ['snapshot_time'])
    except:
        pass  # Таблица может не существовать

    # Для traffic_source_stats_daily (если существует)
    try:
        op.create_index('idx_ts_stats_snapshot', 'traffic_source_stats_daily', ['snapshot_time'])
    except:
        pass

    # Для network_stats_daily (если существует)
    try:
        op.create_index('idx_network_stats_snapshot', 'network_stats_daily', ['snapshot_time'])
    except:
        pass

    # === ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ===
    # Добавляем настройки хранения данных
    op.execute("""
        INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description, is_editable, min_value, max_value)
        VALUES
            ('data.retention_days', '90', 'int', 'data', 'Период хранения дневной статистики (дней)', 1, 7, 365),
            ('data.cleanup_aggressive', 'false', 'bool', 'data', 'Агрессивная очистка старых данных', 1, NULL, NULL),
            ('schedule.cleanup', '0 3 * * 0', 'string', 'schedule', 'Расписание очистки старых данных (cron)', 1, NULL, NULL)
    """)


def downgrade():
    """Удаление индексов и настроек"""

    # Удаляем индексы для campaigns
    op.drop_index('idx_campaigns_active_group', 'campaigns')
    op.drop_index('idx_campaigns_created_at', 'campaigns')
    op.drop_index('idx_campaigns_last_seen', 'campaigns')
    op.drop_index('idx_campaigns_name', 'campaigns')

    # Удаляем индексы для campaign_stats_daily
    op.drop_index('idx_stats_daily_active_campaigns', 'campaign_stats_daily')
    op.drop_index('idx_stats_daily_cost_clicks', 'campaign_stats_daily')

    # Удаляем индексы snapshot_time
    op.drop_index('idx_campaign_stats_snapshot', 'campaign_stats_daily')

    try:
        op.drop_index('idx_stats_period_snapshot', 'stats_period')
    except:
        pass

    try:
        op.drop_index('idx_ts_stats_snapshot', 'traffic_source_stats_daily')
    except:
        pass

    try:
        op.drop_index('idx_network_stats_snapshot', 'network_stats_daily')
    except:
        pass

    # Удаляем настройки
    op.execute("""
        DELETE FROM app_settings
        WHERE key IN ('data.retention_days', 'data.cleanup_aggressive', 'schedule.cleanup')
    """)
