#!/bin/bash
set -e

# Цвета для вывода (ANSI коды, БЕЗ ЭМОДЗИ!)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
# Определяем пути - внутри Docker контейнера или локально
if [ -d "/app/binom_assistant" ]; then
    # Работаем внутри Docker контейнера
    # Проверяем оба возможных места для БД
    if [ -f "/app/binom_assistant/data/binom_assistant.db" ]; then
        DB_PATH="/app/binom_assistant/data/binom_assistant.db"
    else
        DB_PATH="/app/data/binom_assistant.db"
    fi
    BACKUP_DIR="/app/backups"
else
    # Работаем локально (на хосте)
    # Проверяем оба возможных места для БД
    if [ -f "./binom_assistant/data/binom_assistant.db" ]; then
        DB_PATH="./binom_assistant/data/binom_assistant.db"
    else
        DB_PATH="./data/binom_assistant.db"
    fi
    BACKUP_DIR="./backups"
fi

KEEP_BACKUPS=7  # Хранить последние N бэкапов
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="$BACKUP_DIR/binom_assistant_$TIMESTAMP.db"
BACKUP_FILE_GZ="$BACKUP_FILE.gz"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Binom Assistant - Backup Database   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Проверка существования базы данных
echo -e "${YELLOW}[1/4] Checking database...${NC}"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${RED}[ERROR]${NC} Database not found: $DB_PATH"
    exit 1
fi

DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
echo -e "${GREEN}[OK]${NC} Database found (size: $DB_SIZE)"
echo ""

# Создание директории для бэкапов
echo -e "${YELLOW}[2/4] Preparing backup directory...${NC}"
mkdir -p "$BACKUP_DIR"
echo -e "${GREEN}[OK]${NC} Backup directory ready: $BACKUP_DIR"
echo ""

# Создание бэкапа
echo -e "${YELLOW}[3/4] Creating backup...${NC}"
echo "Backup file: $BACKUP_FILE"

# Копируем базу
cp "$DB_PATH" "$BACKUP_FILE"

# Сжимаем в gzip
if command -v gzip &> /dev/null; then
    gzip "$BACKUP_FILE"
    FINAL_BACKUP="$BACKUP_FILE_GZ"
    BACKUP_SIZE=$(du -h "$FINAL_BACKUP" | cut -f1)
    echo -e "${GREEN}[OK]${NC} Backup created and compressed: $BACKUP_SIZE"
else
    FINAL_BACKUP="$BACKUP_FILE"
    BACKUP_SIZE=$(du -h "$FINAL_BACKUP" | cut -f1)
    echo -e "${GREEN}[OK]${NC} Backup created (not compressed): $BACKUP_SIZE"
fi
echo ""

# Удаление старых бэкапов
echo -e "${YELLOW}[4/4] Cleaning old backups...${NC}"
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/binom_assistant_*.db* 2>/dev/null | wc -l)

if [ "$BACKUP_COUNT" -gt "$KEEP_BACKUPS" ]; then
    echo "Found $BACKUP_COUNT backups, keeping last $KEEP_BACKUPS"

    # Удаляем старые бэкапы (оставляем последние KEEP_BACKUPS)
    ls -1t "$BACKUP_DIR"/binom_assistant_*.db* | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm

    DELETED=$((BACKUP_COUNT - KEEP_BACKUPS))
    echo -e "${GREEN}[OK]${NC} Deleted $DELETED old backup(s)"
else
    echo -e "${BLUE}[INFO]${NC} Found $BACKUP_COUNT backup(s), no cleanup needed"
fi
echo ""

# Итоговая информация
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Backup Complete!                     ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Backup file: ${GREEN}$FINAL_BACKUP${NC}"
echo -e "Backup size: ${GREEN}$BACKUP_SIZE${NC}"
echo ""
echo "List of all backups:"
ls -lh "$BACKUP_DIR"/binom_assistant_*.db* 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "To restore this backup:"
echo "  1. Stop container: docker compose down"
echo "  2. Restore DB: gunzip -c $FINAL_BACKUP > $DB_PATH"
echo "     (or: cp $FINAL_BACKUP $DB_PATH if not compressed)"
echo "  3. Start container: docker compose up -d"
echo ""
