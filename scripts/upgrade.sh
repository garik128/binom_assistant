#!/bin/bash
set -e

# Цвета для вывода (ANSI коды, БЕЗ ЭМОДЗИ!)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
CONTAINER_NAME="binom-assistant"
DOCKER_IMAGE="ghcr.io/garik128/binom_assistant"
VERSION="${1:-latest}"  # Версия из аргумента или latest

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Binom Assistant - Upgrade            ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Проверка что docker-compose.yml существует
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}[ERROR]${NC} docker-compose.yml not found"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Получение текущей версии
echo -e "${YELLOW}[1/7] Checking current version...${NC}"
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    CURRENT_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    echo -e "${BLUE}[INFO]${NC} Current image: $CURRENT_IMAGE"
else
    echo -e "${YELLOW}[WARNING]${NC} Container is not running"
    CURRENT_IMAGE="none"
fi
echo ""

# Обновление кода из Git
echo -e "${YELLOW}[2/9] Updating code from Git...${NC}"
if [ -d ".git" ]; then
    echo "Stashing local changes..."
    git stash
    echo "Pulling latest code..."
    if git pull; then
        echo -e "${GREEN}[OK]${NC} Code updated from Git"

        # Восстанавливаем права на выполнение скриптов после git pull
        echo "Fixing script permissions..."
        chmod +x scripts/*.sh 2>/dev/null || true
    else
        echo -e "${RED}[ERROR]${NC} Git pull failed"
        exit 1
    fi
else
    echo -e "${YELLOW}[WARNING]${NC} Not a git repository, skipping git update"
fi
echo ""

# Автоматический бэкап
echo -e "${YELLOW}[3/9] Creating automatic backup...${NC}"
if [ -f "scripts/backup.sh" ]; then
    # Запускаем backup.sh напрямую без захвата вывода (чтобы избежать зависания)
    if ./scripts/backup.sh; then
        # Находим последний созданный бэкап
        BACKUP_FILE=$(ls -t backups/binom_assistant_*.db* 2>/dev/null | head -1)
        if [ -n "$BACKUP_FILE" ]; then
            echo -e "${BLUE}[INFO]${NC} Backup saved to: $BACKUP_FILE"
        fi
    else
        echo -e "${RED}[ERROR]${NC} Backup failed"
        read -p "Continue without backup? [y/N]: " continue_without_backup
        if [[ ! "$continue_without_backup" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}[WARNING]${NC} Backup script not found, skipping backup"
fi
echo ""

# Сохранение текущего образа для возможности отката
echo -e "${YELLOW}[4/9] Saving current image for rollback...${NC}"
if [ "$CURRENT_IMAGE" != "none" ] && [ "$CURRENT_IMAGE" != "unknown" ]; then
    docker tag "$CURRENT_IMAGE" "${DOCKER_IMAGE}:backup-before-upgrade" 2>/dev/null || true
    echo -e "${GREEN}[OK]${NC} Current image tagged for rollback"
else
    echo -e "${YELLOW}[WARNING]${NC} No current image to save"
fi
echo ""

# Скачивание новой версии
echo -e "${YELLOW}[5/9] Pulling new version...${NC}"
echo "Target: ${DOCKER_IMAGE}:${VERSION}"

# Изменяем docker-compose.yml временно если указана конкретная версия
if [ "$VERSION" != "latest" ]; then
    sed -i.bak "s|${DOCKER_IMAGE}:.*|${DOCKER_IMAGE}:${VERSION}|g" docker-compose.yml
fi

if docker compose pull; then
    echo -e "${GREEN}[OK]${NC} New image pulled successfully"
else
    echo -e "${RED}[ERROR]${NC} Failed to pull new image"

    # Откатываем изменения в docker-compose.yml
    if [ -f "docker-compose.yml.bak" ]; then
        mv docker-compose.yml.bak docker-compose.yml
    fi

    exit 1
fi

# Удаляем backup файл
rm -f docker-compose.yml.bak
echo ""

# Перезапуск с новым образом
echo -e "${YELLOW}[6/9] Restarting with new version...${NC}"

# Используем --force-recreate чтобы пересоздать контейнер и обновить volume mounts
if docker compose up -d --force-recreate; then
    echo -e "${GREEN}[OK]${NC} Container restarted"
else
    echo -e "${RED}[ERROR]${NC} Failed to restart container"
    echo ""
    echo "Attempting rollback..."

    # Откат к предыдущей версии
    if docker image inspect "${DOCKER_IMAGE}:backup-before-upgrade" &> /dev/null; then
        docker tag "${DOCKER_IMAGE}:backup-before-upgrade" "${DOCKER_IMAGE}:latest"
        docker compose up -d
        echo -e "${YELLOW}[WARNING]${NC} Rolled back to previous version"
    fi

    exit 1
fi
echo ""

# Ожидание healthcheck
echo -e "${YELLOW}[7/9] Waiting for health check...${NC}"
echo "(This may take up to 60 seconds)"
echo ""

HEALTH_OK=false
for i in {1..60}; do
    if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}[OK]${NC} Application is healthy!"
        HEALTH_OK=true
        break
    fi

    echo -n "."
    sleep 1
done

echo ""

if [ "$HEALTH_OK" = false ]; then
    echo -e "${RED}[ERROR]${NC} Health check failed"
    echo ""
    echo "Container logs:"
    docker logs --tail 50 "$CONTAINER_NAME"
    echo ""
    echo -e "${YELLOW}[WARNING]${NC} Upgrade may have failed"
    echo "Check logs: docker logs -f $CONTAINER_NAME"
    echo ""

    read -p "Rollback to previous version? [Y/n]: " rollback_choice

    if [[ ! "$rollback_choice" =~ ^[Nn]$ ]]; then
        echo "Rolling back..."

        if docker image inspect "${DOCKER_IMAGE}:backup-before-upgrade" &> /dev/null; then
            docker tag "${DOCKER_IMAGE}:backup-before-upgrade" "${DOCKER_IMAGE}:latest"
            docker compose up -d
            echo -e "${GREEN}[OK]${NC} Rolled back to previous version"
        else
            echo -e "${RED}[ERROR]${NC} Backup image not found, cannot rollback"
        fi
    fi

    exit 1
fi
echo ""

# Получение информации о новой версии
echo -e "${YELLOW}[8/9] Checking new version...${NC}"
NEW_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
echo -e "${GREEN}[OK]${NC} New image: $NEW_IMAGE"

# Проверяем что файлы обновились внутри контейнера
if docker exec "$CONTAINER_NAME" test -f /app/binom_assistant/interfaces/web/static/css/main.css; then
    CONTAINER_CSS_DATE=$(docker exec "$CONTAINER_NAME" stat -c %y /app/binom_assistant/interfaces/web/static/css/main.css 2>/dev/null | cut -d'.' -f1 || echo "unknown")
    echo -e "${BLUE}[INFO]${NC} CSS file in container: $CONTAINER_CSS_DATE"
fi
echo ""

# Восстановление локальных изменений из stash
echo -e "${YELLOW}[9/9] Restoring local changes...${NC}"
if [ -d ".git" ]; then
    STASH_COUNT=$(git stash list | wc -l)
    if [ "$STASH_COUNT" -gt 0 ]; then
        echo "Applying stashed changes..."
        if git stash pop; then
            echo -e "${GREEN}[OK]${NC} Local changes restored"
        else
            echo -e "${YELLOW}[WARNING]${NC} Conflict while restoring changes"
            echo "Your changes are still in stash. Use 'git stash pop' manually to restore them."
        fi
    else
        echo -e "${BLUE}[INFO]${NC} No stashed changes to restore"
    fi
else
    echo -e "${BLUE}[INFO]${NC} Not a git repository, skipping"
fi
echo ""

# Показать changelog если доступен
if [ "$VERSION" != "latest" ]; then
    echo "Changelog URL:"
    echo "  https://github.com/garik128/binom_assistant/releases/tag/$VERSION"
    echo ""
fi

# Итоговая информация
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Upgrade Complete!                    ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Previous: ${YELLOW}$CURRENT_IMAGE${NC}"
echo -e "Current:  ${GREEN}$NEW_IMAGE${NC}"
echo ""

if [ -n "$BACKUP_FILE" ]; then
    echo -e "${GREEN}Database backup:${NC} $BACKUP_FILE"
    echo ""
fi

echo "Useful commands:"
echo "  View logs:    docker logs -f $CONTAINER_NAME"
echo "  Check status: docker ps"
echo "  Rollback:     docker tag ${DOCKER_IMAGE}:backup-before-upgrade ${DOCKER_IMAGE}:latest && docker compose up -d"
echo ""
echo "To remove backup image:"
echo "  docker rmi ${DOCKER_IMAGE}:backup-before-upgrade"
echo ""
