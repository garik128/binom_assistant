"""
Миграция 0009: Добавление таблицы chat_templates

Создает таблицу для хранения шаблонов промптов:
- chat_templates

Дата: 2025-11-06
"""
from alembic import op
import sqlalchemy as sa


# Ревизии
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    """Создание таблицы chat_templates"""
    op.create_table(
        'chat_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=False, server_default='message'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id')
    )

    # Добавляем индекс для сортировки по дате
    op.create_index('idx_chat_templates_created_at', 'chat_templates', ['created_at'])


def downgrade():
    """Удаление таблицы chat_templates"""
    # Удаляем индекс
    op.drop_index('idx_chat_templates_created_at', 'chat_templates')

    # Удаляем таблицу
    op.drop_table('chat_templates')
