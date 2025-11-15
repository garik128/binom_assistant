"""
Миграция 0010: Исправление колонки background_tasks

Переименовывает колонку 'message' в 'progress_message' в таблице background_tasks
для соответствия с моделью BackgroundTask.

Дата: 2025-11-12
"""
from alembic import op
import sqlalchemy as sa


# Ревизии
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    """Переименование колонки message в progress_message"""

    # SQLite не поддерживает ALTER COLUMN RENAME напрямую
    # Нужно пересоздать таблицу

    # Создаем временную таблицу с правильной структурой
    op.create_table(
        'background_tasks_new',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('progress_message', sa.String(length=500), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Копируем данные из старой таблицы (переименовываем message в progress_message)
    op.execute("""
        INSERT INTO background_tasks_new
        (id, task_type, status, progress, progress_message, result, error, created_at, started_at, completed_at)
        SELECT
            id, task_type, status, progress, message, result, error, created_at, started_at, completed_at
        FROM background_tasks
    """)

    # Удаляем старую таблицу
    op.drop_table('background_tasks')

    # Переименовываем новую таблицу
    op.rename_table('background_tasks_new', 'background_tasks')

    # Восстанавливаем индексы
    op.create_index('idx_background_tasks_type', 'background_tasks', ['task_type'])
    op.create_index('idx_background_tasks_status', 'background_tasks', ['status'])
    op.create_index('idx_background_tasks_created_at', 'background_tasks', ['created_at'])

    # Добавляем настройку для отслеживания первого запуска
    op.execute("""
        INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description, is_editable)
        VALUES ('system.first_run', 'true', 'string', 'system', 'Флаг первого запуска системы', 0)
    """)


def downgrade():
    """Возврат колонки progress_message в message"""

    # Создаем временную таблицу со старой структурой
    op.create_table(
        'background_tasks_old',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('total', sa.Integer(), default=100),
        sa.Column('message', sa.String(length=500), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Копируем данные обратно
    op.execute("""
        INSERT INTO background_tasks_old
        (id, task_type, status, progress, message, result, error, created_at, started_at, completed_at)
        SELECT
            id, task_type, status, progress, progress_message, result, error, created_at, started_at, completed_at
        FROM background_tasks
    """)

    # Удаляем новую таблицу
    op.drop_table('background_tasks')

    # Переименовываем обратно
    op.rename_table('background_tasks_old', 'background_tasks')

    # Восстанавливаем индексы
    op.create_index('idx_background_tasks_type', 'background_tasks', ['task_type'])
    op.create_index('idx_background_tasks_status', 'background_tasks', ['status'])
    op.create_index('idx_background_tasks_started_at', 'background_tasks', ['started_at'])
