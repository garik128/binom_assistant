"""Add stats_period table

Revision ID: 0003
Revises: 0002
Create Date: 2025-10-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создание таблицы stats_period для хранения агрегированных данных за период
    """
    # Таблица период статистики
    op.create_table(
        'stats_period',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
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
        sa.UniqueConstraint('campaign_id', 'period_type', 'period_start', 'period_end', name='unique_campaign_period')
    )

    # Индексы для stats_period
    op.create_index('idx_stats_period_campaign_id', 'stats_period', ['campaign_id'])
    op.create_index('idx_stats_period_type', 'stats_period', ['period_type'])
    op.create_index('idx_stats_period_dates', 'stats_period', ['period_start', 'period_end'])


def downgrade() -> None:
    """
    Удаление таблицы stats_period
    """
    op.drop_index('idx_stats_period_dates', table_name='stats_period')
    op.drop_index('idx_stats_period_type', table_name='stats_period')
    op.drop_index('idx_stats_period_campaign_id', table_name='stats_period')
    op.drop_table('stats_period')
