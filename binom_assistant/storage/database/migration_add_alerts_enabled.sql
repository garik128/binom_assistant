-- Миграция: Добавление поля alerts_enabled в module_configs
-- Дата: 2025-11-01
-- Описание: Добавляет поле alerts_enabled для управления генерацией алертов в Telegram

-- Добавляем колонку alerts_enabled (по умолчанию FALSE)
ALTER TABLE module_configs
ADD COLUMN alerts_enabled BOOLEAN DEFAULT FALSE;

-- Устанавливаем alerts_enabled = TRUE для критических модулей
UPDATE module_configs
SET alerts_enabled = TRUE
WHERE module_id IN (
    'bleeding_detector',
    'zero_approval_alert',
    'spend_spike_monitor',
    'waste_campaign_finder',
    'traffic_quality_crash',
    'squeezed_offer'
);

-- Создаем индекс для быстрой фильтрации модулей с включенными алертами
CREATE INDEX IF NOT EXISTS idx_module_configs_alerts_enabled
ON module_configs(alerts_enabled)
WHERE alerts_enabled = TRUE;
