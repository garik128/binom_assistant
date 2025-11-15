-- Миграция: Добавление настроек хранения данных
-- Дата: 2025-11-02
-- Описание: Настройки для управления retention и cleanup данных

-- Добавляем настройки хранения данных
INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description, is_editable, min_value, max_value)
VALUES
    ('data.retention_days', '90', 'int', 'data', 'Период хранения дневной статистики (дней)', 1, 7, 365),
    ('data.cleanup_aggressive', 'false', 'bool', 'data', 'Агрессивная очистка старых данных', 1, NULL, NULL),
    ('schedule.cleanup', '0 3 * * 0', 'string', 'schedule', 'Расписание очистки старых данных (cron)', 1, NULL, NULL);
