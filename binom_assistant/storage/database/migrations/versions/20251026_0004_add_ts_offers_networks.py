"""Add traffic sources, offers, networks tables

Revision ID: 0004
Revises: 0003
Create Date: 2025-10-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создание таблиц для источников трафика, офферов и партнерских сетей
    """
    # 1. Обновить campaigns - добавить ts_id
    op.add_column('campaigns', sa.Column('ts_id', sa.Integer(), nullable=True))
    op.create_index('idx_campaigns_ts_id', 'campaigns', ['ts_id'])

    # 2. Traffic Sources
    op.create_table(
        'traffic_sources',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.Boolean(), default=True),
        sa.Column('ts_integration_id', sa.Integer()),
        sa.Column('postback_url', sa.Text()),
        sa.Column('external_param_name', sa.String(100)),
        sa.Column('external_param_value', sa.String(100)),
        sa.Column('total_campaigns', sa.Integer(), default=0),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime())
    )
    op.create_index('idx_ts_name', 'traffic_sources', ['name'])
    op.create_index('idx_ts_status', 'traffic_sources', ['status'])

    # 3. Traffic Source Stats Daily
    op.create_table(
        'traffic_source_stats_daily',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ts_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), default=0),
        sa.Column('cost', sa.Numeric(10, 2), default=0),
        sa.Column('leads', sa.Integer(), default=0),
        sa.Column('revenue', sa.Numeric(10, 2), default=0),
        sa.Column('roi', sa.Numeric(10, 2)),
        sa.Column('cr', sa.Numeric(10, 4)),
        sa.Column('cpc', sa.Numeric(10, 4)),
        sa.Column('a_leads', sa.Integer(), default=0),
        sa.Column('h_leads', sa.Integer(), default=0),
        sa.Column('r_leads', sa.Integer(), default=0),
        sa.Column('approve', sa.Numeric(10, 2)),
        sa.Column('active_campaigns', sa.Integer(), default=0),
        sa.Column('snapshot_time', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['ts_id'], ['traffic_sources.id']),
        sa.UniqueConstraint('ts_id', 'date', name='unique_ts_date')
    )
    op.create_index('idx_ts_stats_ts_id', 'traffic_source_stats_daily', ['ts_id'])
    op.create_index('idx_ts_stats_date', 'traffic_source_stats_daily', ['date'])

    # 4. Affiliate Networks
    op.create_table(
        'affiliate_networks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.Boolean(), default=True),
        sa.Column('postback_url', sa.Text()),
        sa.Column('offer_url_template', sa.Text()),
        sa.Column('total_offers', sa.Integer(), default=0),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime())
    )
    op.create_index('idx_network_name', 'affiliate_networks', ['name'])
    op.create_index('idx_network_status', 'affiliate_networks', ['status'])

    # 5. Network Stats Daily
    op.create_table(
        'network_stats_daily',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('network_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), default=0),
        sa.Column('leads', sa.Integer(), default=0),
        sa.Column('revenue', sa.Numeric(10, 2), default=0),
        sa.Column('cost', sa.Numeric(10, 2), default=0),
        sa.Column('a_leads', sa.Integer(), default=0),
        sa.Column('h_leads', sa.Integer(), default=0),
        sa.Column('r_leads', sa.Integer(), default=0),
        sa.Column('approve', sa.Numeric(10, 2)),
        sa.Column('roi', sa.Numeric(10, 2)),
        sa.Column('profit', sa.Numeric(10, 2)),
        sa.Column('active_offers', sa.Integer(), default=0),
        sa.Column('snapshot_time', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['network_id'], ['affiliate_networks.id']),
        sa.UniqueConstraint('network_id', 'date', name='unique_network_date')
    )
    op.create_index('idx_network_stats_network_id', 'network_stats_daily', ['network_id'])
    op.create_index('idx_network_stats_date', 'network_stats_daily', ['date'])

    # 6. Offers
    op.create_table(
        'offers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('network_id', sa.Integer()),
        sa.Column('geo', sa.String(100)),
        sa.Column('payout', sa.Numeric(10, 2)),
        sa.Column('currency', sa.String(10), default='usd'),
        sa.Column('url', sa.Text()),
        sa.Column('group_id', sa.Integer()),
        sa.Column('group_name', sa.String(255)),
        sa.Column('status', sa.Boolean(), default=True),
        sa.Column('is_banned', sa.Boolean(), default=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['network_id'], ['affiliate_networks.id'])
    )
    op.create_index('idx_offer_name', 'offers', ['name'])
    op.create_index('idx_offer_network', 'offers', ['network_id'])
    op.create_index('idx_offer_geo', 'offers', ['geo'])
    op.create_index('idx_offer_status', 'offers', ['status'])

    # 7. Offer Stats Daily
    op.create_table(
        'offer_stats_daily',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('offer_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), default=0),
        sa.Column('leads', sa.Integer(), default=0),
        sa.Column('revenue', sa.Numeric(10, 2), default=0),
        sa.Column('cost', sa.Numeric(10, 2), default=0),
        sa.Column('a_leads', sa.Integer(), default=0),
        sa.Column('h_leads', sa.Integer(), default=0),
        sa.Column('r_leads', sa.Integer(), default=0),
        sa.Column('cr', sa.Numeric(10, 4)),
        sa.Column('approve', sa.Numeric(10, 2)),
        sa.Column('epc', sa.Numeric(10, 4)),
        sa.Column('roi', sa.Numeric(10, 2)),
        sa.Column('snapshot_time', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id']),
        sa.UniqueConstraint('offer_id', 'date', name='unique_offer_date')
    )
    op.create_index('idx_offer_stats_offer_id', 'offer_stats_daily', ['offer_id'])
    op.create_index('idx_offer_stats_date', 'offer_stats_daily', ['date'])


def downgrade() -> None:
    """
    Удаление таблиц для источников трафика, офферов и партнерских сетей
    """
    op.drop_table('offer_stats_daily')
    op.drop_table('offers')
    op.drop_table('network_stats_daily')
    op.drop_table('affiliate_networks')
    op.drop_table('traffic_source_stats_daily')
    op.drop_table('traffic_sources')

    op.drop_index('idx_campaigns_ts_id', 'campaigns')
    op.drop_column('campaigns', 'ts_id')
