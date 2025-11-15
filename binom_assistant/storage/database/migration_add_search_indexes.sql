-- Миграция: Добавление индексов для поиска по названиям и датам
-- Дата: 2025-10-25
-- TODO 10: Добавить индексы для поиска по названиям и датам

-- Индекс для поиска по имени кампании
CREATE INDEX IF NOT EXISTS idx_campaigns_name ON campaigns(current_name);

-- Индекс для фильтрации по последнему обновлению (с сортировкой DESC)
CREATE INDEX IF NOT EXISTS idx_campaigns_last_seen ON campaigns(last_seen DESC);

-- Индекс для сортировки по дате создания (с сортировкой DESC)
CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns(created_at DESC);

-- Композитный частичный индекс для типовых запросов (активные кампании + группа)
-- Этот индекс оптимизирует запросы вида: WHERE is_active = TRUE AND group_name = 'Nutra'
CREATE INDEX IF NOT EXISTS idx_campaigns_active_group ON campaigns(is_active, group_name)
WHERE is_active = TRUE;
