-- Миграция для добавления настройки паузы между API запросами
-- Дата: 2025-11-05

-- Добавляем настройку collector.api_pause если её нет
INSERT OR IGNORE INTO app_settings (key, value, value_type, category, description)
VALUES (
    'collector.api_pause',
    '3.0',
    'float',
    'collector',
    'Пауза в секундах между блоками запросов к Binom API'
);
