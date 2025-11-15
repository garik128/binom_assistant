#!/bin/bash
set -e

# Цвета для вывода (ANSI коды)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Binom Assistant - Starting Container ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. Создаем необходимые директории
echo -e "${YELLOW}[1/4] Checking directories...${NC}"
mkdir -p /app/data /app/logs
echo -e "${GREEN}[OK]${NC} Directories ready"
echo ""

# 2. Проверяем наличие alembic.ini для миграций
echo -e "${YELLOW}[2/4] Checking database migrations...${NC}"
ALEMBIC_INI="/app/binom_assistant/storage/database/alembic.ini"
ALEMBIC_DIR="/app/binom_assistant/storage/database/migrations"

if [ -f "$ALEMBIC_INI" ] && [ -d "$ALEMBIC_DIR" ]; then
    echo -e "${BLUE}Found alembic configuration, running migrations...${NC}"
    cd /app/binom_assistant/storage/database

    # Запускаем миграции
    if alembic upgrade head; then
        echo -e "${GREEN}[OK]${NC} Database migrations applied successfully"
    else
        echo -e "${RED}[WARNING]${NC} Failed to apply migrations, continuing anyway..."
    fi

    cd /app
else
    echo -e "${YELLOW}[SKIP]${NC} No alembic configuration found, skipping migrations"
fi
echo ""

# 3. Проверяем переменные окружения
echo -e "${YELLOW}[3/4] Checking environment...${NC}"
if [ -f "/app/binom_assistant/.env" ]; then
    echo -e "${GREEN}[OK]${NC} .env file found"
elif [ -f "/app/.env" ]; then
    echo -e "${GREEN}[OK]${NC} .env file found in root"
else
    echo -e "${YELLOW}[WARNING]${NC} No .env file found, using environment variables"
fi
echo ""

# 4. Готово к запуску
echo -e "${YELLOW}[4/4] Starting application...${NC}"
echo -e "${GREEN}[OK]${NC} All checks passed"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Binom Assistant Ready                 ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Запускаем команду, переданную в CMD
exec "$@"
