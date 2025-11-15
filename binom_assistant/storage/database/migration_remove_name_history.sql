-- Миграция: Удаление поля name_history из таблицы campaigns
-- Дата: 2025-10-25
-- Причина: Дублирование данных - история имен хранится в таблице name_changes

-- SQLite не поддерживает ALTER TABLE DROP COLUMN напрямую
-- Нужно пересоздать таблицу

-- Шаг 1: Создаем временную таблицу с новой структурой
CREATE TABLE campaigns_new (
    internal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    binom_id INTEGER NOT NULL UNIQUE,
    current_name VARCHAR(255) NOT NULL,
    group_name VARCHAR(255),
    ts_name VARCHAR(255),
    domain_name VARCHAR(255),
    is_cpl_mode BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMP NOT NULL,
    last_seen TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Шаг 2: Копируем данные (без name_history)
INSERT INTO campaigns_new (
    internal_id,
    binom_id,
    current_name,
    group_name,
    ts_name,
    domain_name,
    is_cpl_mode,
    first_seen,
    last_seen,
    created_at,
    updated_at
)
SELECT
    internal_id,
    binom_id,
    current_name,
    group_name,
    ts_name,
    domain_name,
    is_cpl_mode,
    first_seen,
    last_seen,
    created_at,
    updated_at
FROM campaigns;

-- Шаг 3: Удаляем старую таблицу
DROP TABLE campaigns;

-- Шаг 4: Переименовываем новую таблицу
ALTER TABLE campaigns_new RENAME TO campaigns;

-- Шаг 5: Пересоздаем индексы
CREATE INDEX idx_campaigns_binom_id ON campaigns(binom_id);
CREATE INDEX idx_campaigns_group ON campaigns(group_name);
CREATE INDEX idx_campaigns_ts ON campaigns(ts_name);
CREATE INDEX idx_campaigns_cpl ON campaigns(is_cpl_mode);
