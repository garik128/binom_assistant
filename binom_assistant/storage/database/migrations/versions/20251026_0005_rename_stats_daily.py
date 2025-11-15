"""rename stats_daily to campaign_stats_daily

Revision ID: 0005
Revises: 0004
Create Date: 2025-10-26 03:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    """Переименовываем таблицу stats_daily в campaign_stats_daily"""
    # SQLite не поддерживает ALTER TABLE RENAME напрямую, поэтому используем op.rename_table
    op.rename_table('stats_daily', 'campaign_stats_daily')


def downgrade():
    """Откатываем переименование"""
    op.rename_table('campaign_stats_daily', 'stats_daily')
