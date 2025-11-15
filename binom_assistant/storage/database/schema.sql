-- Схема базы данных Binom Assistant
-- SQLite

-- Кампании
CREATE TABLE IF NOT EXISTS campaigns (
    internal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    binom_id INTEGER NOT NULL UNIQUE,               -- ID в Binom
    current_name VARCHAR(255) NOT NULL,             -- Текущее имя
    group_name VARCHAR(255),                        -- Группа (Nutra, Dating, etc)
    ts_name VARCHAR(255),                           -- Источник трафика
    domain_name VARCHAR(255),                       -- Домен
    is_cpl_mode BOOLEAN DEFAULT FALSE,              -- CPL или CPA кампания
    is_active BOOLEAN DEFAULT TRUE,                 -- Активна ли кампания
    status VARCHAR(20) DEFAULT 'active',            -- Статус: active, paused
    first_seen TIMESTAMP NOT NULL,                  -- Когда впервые увидели
    last_seen TIMESTAMP NOT NULL,                   -- Последнее обновление
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска
CREATE INDEX idx_campaigns_binom_id ON campaigns(binom_id);
CREATE INDEX idx_campaigns_group ON campaigns(group_name);
CREATE INDEX idx_campaigns_ts ON campaigns(ts_name);
CREATE INDEX idx_campaigns_cpl ON campaigns(is_cpl_mode);
CREATE INDEX idx_campaigns_active ON campaigns(is_active);
CREATE INDEX idx_campaigns_status ON campaigns(status);

-- Индексы для поиска по названиям и датам (TODO 10)
CREATE INDEX idx_campaigns_name ON campaigns(current_name);
CREATE INDEX idx_campaigns_last_seen ON campaigns(last_seen DESC);
CREATE INDEX idx_campaigns_created_at ON campaigns(created_at DESC);

-- Композитный индекс для типовых запросов (активные + группа)
CREATE INDEX idx_campaigns_active_group ON campaigns(is_active, group_name)
WHERE is_active = TRUE;

-- Дневная статистика
CREATE TABLE IF NOT EXISTS stats_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,                   -- Ссылка на campaigns.internal_id
    date DATE NOT NULL,                             -- Дата статистики

    -- Основные метрики
    clicks INTEGER DEFAULT 0,
    leads INTEGER DEFAULT 0,
    cost DECIMAL(10, 2) DEFAULT 0,
    revenue DECIMAL(10, 2) DEFAULT 0,

    -- Производные метрики
    roi DECIMAL(10, 2),                             -- Return on Investment
    cr DECIMAL(10, 4),                              -- Conversion Rate
    cpc DECIMAL(10, 4),                             -- Cost per Click
    approve DECIMAL(10, 2),                         -- Процент апрува (приходит от Binom API, формула: a_leads/(a_leads+h_leads+r_leads)*100)

    -- Лиды по статусам
    a_leads INTEGER DEFAULT 0,                      -- Approved leads
    h_leads INTEGER DEFAULT 0,                      -- Hold leads
    r_leads INTEGER DEFAULT 0,                      -- Rejected leads

    -- Дополнительно
    lead_price DECIMAL(10, 2),                      -- Цена лида
    profit DECIMAL(10, 2),                          -- Прибыль
    epc DECIMAL(10, 4),                             -- Earnings per Click

    -- Мета-информация
    snapshot_time TIMESTAMP NOT NULL,               -- Когда получили данные
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id) REFERENCES campaigns(internal_id) ON DELETE CASCADE,
    UNIQUE(campaign_id, date)                       -- Одна запись на кампанию в день
);

-- Индексы для аналитики
CREATE INDEX idx_stats_campaign ON stats_daily(campaign_id);
CREATE INDEX idx_stats_date ON stats_daily(date);
CREATE INDEX idx_stats_campaign_date ON stats_daily(campaign_id, date);
CREATE INDEX idx_stats_snapshot ON stats_daily(snapshot_time);

-- Индексы для фильтрации шума (cost >= 1$ AND clicks >= 50)
CREATE INDEX idx_stats_daily_cost_clicks ON stats_daily(cost, clicks, campaign_id, date);
CREATE INDEX idx_stats_daily_active_campaigns ON stats_daily(campaign_id, date, cost, clicks)
WHERE cost >= 1.0 AND clicks >= 50;

-- Недельные агрегаты (для быстрого доступа)
CREATE TABLE IF NOT EXISTS stats_weekly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    week_start DATE NOT NULL,                       -- Понедельник недели
    week_end DATE NOT NULL,                         -- Воскресенье недели

    -- Суммарные метрики
    total_clicks INTEGER DEFAULT 0,
    total_leads INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 2) DEFAULT 0,
    total_revenue DECIMAL(10, 2) DEFAULT 0,
    total_profit DECIMAL(10, 2) DEFAULT 0,

    -- Средние метрики
    avg_roi DECIMAL(10, 2),
    avg_cr DECIMAL(10, 4),
    avg_cpc DECIMAL(10, 4),
    avg_approve DECIMAL(10, 2),

    -- Лиды
    total_a_leads INTEGER DEFAULT 0,
    total_h_leads INTEGER DEFAULT 0,
    total_r_leads INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id) REFERENCES campaigns(internal_id) ON DELETE CASCADE,
    UNIQUE(campaign_id, week_start)
);

CREATE INDEX idx_stats_weekly_campaign ON stats_weekly(campaign_id);
CREATE INDEX idx_stats_weekly_start ON stats_weekly(week_start);

-- Алерты (проблемные кампании)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    alert_type VARCHAR(50) NOT NULL,                -- 'no_leads', 'negative_roi', 'cr_drop', etc
    severity VARCHAR(20) DEFAULT 'medium',          -- 'low', 'medium', 'high', 'critical'

    -- Детали алерта
    details JSON,                                   -- Дополнительная информация
    first_detected TIMESTAMP NOT NULL,              -- Когда впервые обнаружено
    last_checked TIMESTAMP NOT NULL,                -- Последняя проверка

    -- Статус
    is_active BOOLEAN DEFAULT TRUE,                 -- Актуален ли алерт
    resolved_at TIMESTAMP,                          -- Когда решена проблема

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id) REFERENCES campaigns(internal_id) ON DELETE CASCADE
);

CREATE INDEX idx_alerts_campaign ON alerts(campaign_id);
CREATE INDEX idx_alerts_type ON alerts(alert_type);
CREATE INDEX idx_alerts_active ON alerts(is_active);

-- Контекст чата (для Telegram бота и веб-чата)
CREATE TABLE IF NOT EXISTS chat_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(100) NOT NULL,                  -- ID пользователя (Telegram ID или session ID)
    session_id VARCHAR(100) NOT NULL,               -- ID сессии

    -- Контекст разговора
    message_role VARCHAR(20) NOT NULL,              -- 'user' или 'assistant'
    message_content TEXT NOT NULL,                  -- Содержимое сообщения

    -- Фокус разговора
    current_campaigns JSON,                         -- Кампании в фокусе
    current_period VARCHAR(50),                     -- Текущий период анализа

    -- Метаданные AI (для аналитики и отладки)
    agent_name VARCHAR(50),                         -- Имя агента (overview, scanner, filter, dynamic, calculator, grouper, weekly)
    model VARCHAR(50),                              -- Модель AI (gpt-4, claude-3-opus, и т.д.)
    tokens_used INTEGER,                            -- Количество использованных токенов
    response_time_ms INTEGER,                       -- Время ответа в миллисекундах

    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_user ON chat_context(user_id);
CREATE INDEX idx_chat_session ON chat_context(session_id);
CREATE INDEX idx_chat_timestamp ON chat_context(timestamp);
CREATE INDEX idx_chat_agent ON chat_context(agent_name);

-- История изменения имен кампаний
CREATE TABLE IF NOT EXISTS name_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    old_name VARCHAR(255),
    new_name VARCHAR(255) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id) REFERENCES campaigns(internal_id) ON DELETE CASCADE
);

CREATE INDEX idx_name_changes_campaign ON name_changes(campaign_id);

-- Системные настройки и кэш
CREATE TABLE IF NOT EXISTS system_cache (
    key VARCHAR(100) PRIMARY KEY,                   -- Ключ (например, 'last_sync_time')
    value TEXT,                                     -- Значение (JSON или строка)
    expires_at TIMESTAMP,                           -- Когда истекает (NULL = не истекает)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
