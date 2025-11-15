-- Миграция для удаления неиспользуемой настройки collector.interval_hours
-- Дата: 2025-11-06
-- Причина: интервал сбора данных управляется через schedule.daily_stats (cron расписание)

DELETE FROM app_settings WHERE key = 'collector.interval_hours';
