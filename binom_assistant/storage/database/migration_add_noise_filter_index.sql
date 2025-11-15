-- Миграция: Добавление индекса для фильтрации шума
-- Дата: 2025-10-25
-- Описание: Композитный индекс для быстрой фильтрации активных кампаний
--           с расходом >= 1$ и кликами >= 50

-- Композитный индекс для оптимизации запросов фильтрации шума
-- Используется в core/data_processor/filter.py
CREATE INDEX IF NOT EXISTS idx_stats_daily_cost_clicks
ON stats_daily(cost, clicks, campaign_id, date);

-- Альтернативный частичный индекс (partial index) для SQLite 3.8.0+
-- Индексирует только записи, которые проходят фильтр шума
CREATE INDEX IF NOT EXISTS idx_stats_daily_active_campaigns
ON stats_daily(campaign_id, date, cost, clicks)
WHERE cost >= 1.0 AND clicks >= 50;

-- Проверка созданных индексов
-- SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='stats_daily';
