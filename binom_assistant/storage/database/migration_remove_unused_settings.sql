-- Миграция для удаления неиспользуемых настроек
-- Дата: 2025-11-06

-- Удаляем настройку расписания очистки (очистка происходит автоматически каждое воскресенье)
DELETE FROM app_settings WHERE key = 'schedule.cleanup';

-- Удаляем настройку агрессивной очистки (не используется в коде)
DELETE FROM app_settings WHERE key = 'data.cleanup_aggressive';
