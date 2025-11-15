-- Миграция: Удаление AI чат функционала
-- Дата: 2025-11-02
-- Описание: Удаляет таблицы chat_sessions, chat_messages, chat_context

-- Удаляем таблицы (порядок важен из-за foreign keys)
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_sessions;
DROP TABLE IF EXISTS chat_context;
