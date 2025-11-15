-- Миграция: Добавление таблицы app_settings для хранения настроек приложения
-- Дата: 2025-11-01
-- Описание: Система настроек с приоритетом БД -> .env -> defaults

-- Создание таблицы app_settings
CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value VARCHAR(500) NOT NULL,
    value_type VARCHAR(20) NOT NULL DEFAULT 'string',
    category VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    is_editable BOOLEAN DEFAULT 1,
    min_value NUMERIC(10, 2),
    max_value NUMERIC(10, 2),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для фильтрации по категории
CREATE INDEX IF NOT EXISTS idx_app_settings_category ON app_settings(category);

-- Индекс для редактируемых настроек
CREATE INDEX IF NOT EXISTS idx_app_settings_editable ON app_settings(is_editable)
WHERE is_editable = 1;

-- Начальные значения (дефолтные настройки)
-- Категория: collector (сбор данных)
INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description, is_editable, min_value, max_value)
VALUES
    ('collector.update_days', '7', 'int', 'collector', 'Период обновления статистики (за сколько дней)', 1, 1, 365),
    ('collector.interval_hours', '1', 'int', 'collector', 'Интервал автоматического сбора данных (часов)', 1, 1, 24);

-- Категория: schedule (расписание задач)
INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description, is_editable)
VALUES
    ('schedule.daily_stats', '0 * * * *', 'string', 'schedule', 'Расписание обновления дневной статистики (cron)', 1),
    ('schedule.weekly_stats', '0 4 * * 1', 'string', 'schedule', 'Расписание расчета недельной статистики (cron)', 1);
