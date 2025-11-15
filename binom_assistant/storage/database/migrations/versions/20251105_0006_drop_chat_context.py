"""
Миграция 0006: Удаление таблицы chat_context

Удаляет устаревшие таблицы AI чат функционала:
- chat_context

Дата: 2025-11-05
"""
from alembic import op


# Ревизии
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    """Удаление таблицы chat_context"""
    # Удаляем индексы
    op.drop_index('idx_chat_context_timestamp', 'chat_context')
    op.drop_index('idx_chat_context_user_session', 'chat_context')

    # Удаляем таблицу
    op.drop_table('chat_context')


def downgrade():
    """Восстановление таблицы chat_context"""
    import sqlalchemy as sa

    # Восстанавливаем таблицу
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
        sa.Column('agent_name', sa.String(length=100), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Восстанавливаем индексы
    op.create_index('idx_chat_context_user_session', 'chat_context', ['user_id', 'session_id'])
    op.create_index('idx_chat_context_timestamp', 'chat_context', ['timestamp'])
