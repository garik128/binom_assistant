"""
Миграция 0007: Создание таблиц модульной системы

Создает таблицы для работы модульной системы анализа:
- module_configs - конфигурация модулей
- module_runs - история запусков
- module_cache - кэш результатов
- background_tasks - фоновые задачи
- app_settings - настройки приложения

Дата: 2025-11-05
"""
from alembic import op
import sqlalchemy as sa


# Ревизии
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    """Создание таблиц модульной системы"""

    # Таблица конфигураций модулей
    op.create_table(
        'module_configs',
        sa.Column('module_id', sa.String(length=100), nullable=False),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('schedule', sa.String(length=100), nullable=True),
        sa.Column('alerts_enabled', sa.Boolean(), default=False),
        sa.Column('timeout_seconds', sa.Integer(), default=30),
        sa.Column('cache_ttl_seconds', sa.Integer(), default=3600),
        sa.Column('params', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('module_id')
    )

    # Таблица истории запусков модулей
    op.create_table(
        'module_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('module_id', sa.String(length=100), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['module_id'], ['module_configs.module_id'], ondelete='CASCADE')
    )

    # Индексы для module_runs
    op.create_index('idx_module_runs_module_id', 'module_runs', ['module_id'])
    op.create_index('idx_module_runs_status', 'module_runs', ['status'])
    op.create_index('idx_module_runs_started_at', 'module_runs', ['started_at'])

    # Таблица кэша модулей
    op.create_table(
        'module_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('module_id', sa.String(length=100), nullable=False),
        sa.Column('cache_key', sa.String(length=200), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module_id', 'cache_key', name='unique_module_cache')
    )

    # Индекс для module_cache
    op.create_index('idx_module_cache_module_id', 'module_cache', ['module_id'])
    op.create_index('idx_module_cache_expires_at', 'module_cache', ['expires_at'])

    # Таблица фоновых задач
    op.create_table(
        'background_tasks',
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

    # Индексы для background_tasks
    op.create_index('idx_background_tasks_type', 'background_tasks', ['task_type'])
    op.create_index('idx_background_tasks_status', 'background_tasks', ['status'])
    op.create_index('idx_background_tasks_started_at', 'background_tasks', ['started_at'])

    # Таблица настроек приложения
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(length=500), nullable=False),
        sa.Column('value_type', sa.String(length=20), nullable=False, server_default='string'),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_editable', sa.Boolean(), default=True),
        sa.Column('min_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('max_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # Индексы для app_settings
    op.create_index('idx_app_settings_category', 'app_settings', ['category'])
    op.create_index('idx_app_settings_editable', 'app_settings', ['is_editable'])

    # Добавляем начальные настройки
    op.execute("""
        INSERT INTO app_settings (key, value, value_type, category, description, is_editable, min_value, max_value)
        VALUES
            ('collector.update_days', '7', 'int', 'collector', 'Период обновления статистики (за сколько дней)', 1, 1, 365),
            ('collector.interval_hours', '1', 'int', 'collector', 'Интервал автоматического сбора данных (часов)', 1, 1, 24),
            ('schedule.daily_stats', '0 * * * *', 'string', 'schedule', 'Расписание обновления дневной статистики (cron)', 1, NULL, NULL),
            ('schedule.weekly_stats', '0 4 * * 1', 'string', 'schedule', 'Расписание расчета недельной статистики (cron)', 1, NULL, NULL)
    """)


def downgrade():
    """Удаление таблиц модульной системы"""

    # Удаляем таблицы в обратном порядке (из-за foreign keys)
    op.drop_table('app_settings')
    op.drop_table('background_tasks')
    op.drop_table('module_cache')
    op.drop_table('module_runs')
    op.drop_table('module_configs')
