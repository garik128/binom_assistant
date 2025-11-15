"""Создание начальной схемы БД

Revision ID: 0001
Revises:
Create Date: 2025-01-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создание всех таблиц
    """
    # Таблица кампаний
    op.create_table(
        'campaigns',
        sa.Column('internal_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('binom_id', sa.Integer(), nullable=False),
        sa.Column('current_name', sa.String(length=255), nullable=False),
        sa.Column('group_name', sa.String(length=255), nullable=True),
        sa.Column('ts_name', sa.String(length=255), nullable=True),
        sa.Column('domain_name', sa.String(length=255), nullable=True),
        sa.Column('is_cpl_mode', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('status', sa.String(length=20), nullable=True, default='active'),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('internal_id'),
        sa.UniqueConstraint('binom_id')
    )

    # Индексы для campaigns
    op.create_index('idx_campaigns_binom_id', 'campaigns', ['binom_id'])
    op.create_index('idx_campaigns_group_name', 'campaigns', ['group_name'])
    op.create_index('idx_campaigns_is_cpl_mode', 'campaigns', ['is_cpl_mode'])
    op.create_index('idx_campaigns_is_active', 'campaigns', ['is_active'])
    op.create_index('idx_campaigns_status', 'campaigns', ['status'])

    # Таблица дневной статистики
    op.create_table(
        'stats_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), nullable=True, default=0),
        sa.Column('leads', sa.Integer(), nullable=True, default=0),
        sa.Column('cost', sa.Numeric(precision=10, scale=2), nullable=True, default=0),
        sa.Column('revenue', sa.Numeric(precision=10, scale=2), nullable=True, default=0),
        sa.Column('roi', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('cr', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('cpc', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('approve', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('a_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('h_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('r_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('lead_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('profit', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('epc', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('snapshot_time', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.internal_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('campaign_id', 'date', name='unique_campaign_date')
    )

    # Индексы для stats_daily
    op.create_index('idx_stats_daily_campaign_id', 'stats_daily', ['campaign_id'])
    op.create_index('idx_stats_daily_date', 'stats_daily', ['date'])
    op.create_index('idx_stats_daily_campaign_date', 'stats_daily', ['campaign_id', 'date'])

    # Таблица недельной статистики
    op.create_table(
        'stats_weekly',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        sa.Column('total_clicks', sa.Integer(), nullable=True, default=0),
        sa.Column('total_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('total_cost', sa.Numeric(precision=10, scale=2), nullable=True, default=0),
        sa.Column('total_revenue', sa.Numeric(precision=10, scale=2), nullable=True, default=0),
        sa.Column('total_profit', sa.Numeric(precision=10, scale=2), nullable=True, default=0),
        sa.Column('avg_roi', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('avg_cr', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('avg_cpc', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('avg_approve', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_a_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('total_h_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('total_r_leads', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.internal_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('campaign_id', 'week_start', name='unique_campaign_week')
    )

    # Индексы для stats_weekly
    op.create_index('idx_stats_weekly_campaign_id', 'stats_weekly', ['campaign_id'])
    op.create_index('idx_stats_weekly_week_start', 'stats_weekly', ['week_start'])

    # Таблица алертов
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=True, default='medium'),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('first_detected', sa.DateTime(), nullable=False),
        sa.Column('last_checked', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.internal_id'], ondelete='CASCADE')
    )

    # Индексы для alerts
    op.create_index('idx_alerts_campaign_id', 'alerts', ['campaign_id'])
    op.create_index('idx_alerts_is_active', 'alerts', ['is_active'])
    op.create_index('idx_alerts_alert_type', 'alerts', ['alert_type'])

    # Таблица контекста чата
    op.create_table(
        'chat_context',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('message_role', sa.String(length=20), nullable=False),
        sa.Column('message_content', sa.Text(), nullable=False),
        sa.Column('current_campaigns', sa.JSON(), nullable=True),
        sa.Column('current_period', sa.String(length=50), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы для chat_context
    op.create_index('idx_chat_context_user_session', 'chat_context', ['user_id', 'session_id'])
    op.create_index('idx_chat_context_timestamp', 'chat_context', ['timestamp'])

    # Таблица изменений имени
    op.create_table(
        'name_changes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('old_name', sa.String(length=255), nullable=True),
        sa.Column('new_name', sa.String(length=255), nullable=False),
        sa.Column('changed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.internal_id'], ondelete='CASCADE')
    )

    # Индексы для name_changes
    op.create_index('idx_name_changes_campaign_id', 'name_changes', ['campaign_id'])
    op.create_index('idx_name_changes_changed_at', 'name_changes', ['changed_at'])

    # Таблица системного кэша
    op.create_table(
        'system_cache',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # Индексы для system_cache
    op.create_index('idx_system_cache_expires_at', 'system_cache', ['expires_at'])


def downgrade() -> None:
    """
    Удаление всех таблиц
    """
    op.drop_table('system_cache')
    op.drop_table('name_changes')
    op.drop_table('chat_context')
    op.drop_table('alerts')
    op.drop_table('stats_weekly')
    op.drop_table('stats_daily')
    op.drop_table('campaigns')
