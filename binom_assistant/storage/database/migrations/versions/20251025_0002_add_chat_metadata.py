"""Добавление метаданных AI в chat_context

Revision ID: 0002
Revises: 0001
Create Date: 2025-10-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавление полей метаданных AI в таблицу chat_context
    """
    # Добавляем новые колонки
    op.add_column('chat_context', sa.Column('agent_name', sa.String(length=50), nullable=True))
    op.add_column('chat_context', sa.Column('model', sa.String(length=50), nullable=True))
    op.add_column('chat_context', sa.Column('tokens_used', sa.Integer(), nullable=True))
    op.add_column('chat_context', sa.Column('response_time_ms', sa.Integer(), nullable=True))

    # Создаем индекс для agent_name
    op.create_index('idx_chat_agent', 'chat_context', ['agent_name'])


def downgrade() -> None:
    """
    Откат изменений - удаление добавленных полей
    """
    # Удаляем индекс
    op.drop_index('idx_chat_agent', table_name='chat_context')

    # Удаляем колонки
    op.drop_column('chat_context', 'response_time_ms')
    op.drop_column('chat_context', 'tokens_used')
    op.drop_column('chat_context', 'model')
    op.drop_column('chat_context', 'agent_name')
