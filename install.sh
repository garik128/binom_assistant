#!/bin/bash
set -e

# Цвета для вывода (ANSI коды, БЕЗ ЭМОДЗИ!)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

REPO_URL="https://github.com/garik128/binom_assistant.git"
INSTALL_DIR="binom_assistant"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Binom Assistant Installer           ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Проверка Docker
echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Docker is not installed"
    echo ""
    echo "Please install Docker first:"
    echo ""
    echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
    echo "  sudo sh get-docker.sh"
    echo ""
    echo "After installation, run this installer again."
    exit 1
fi

DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
echo -e "${GREEN}[OK]${NC} Docker ${DOCKER_VERSION} is installed"

# Проверка Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Docker Compose is not installed"
    echo ""
    echo "Docker Compose v2+ is required."
    echo "It usually comes with Docker, but you may need to update Docker."
    exit 1
fi

COMPOSE_VERSION=$(docker compose version --short)
echo -e "${GREEN}[OK]${NC} Docker Compose ${COMPOSE_VERSION} is installed"
echo ""

# Проверка git
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}[WARNING]${NC} Git is not installed"
    echo ""
    echo "Installing git..."

    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    else
        echo -e "${RED}[ERROR]${NC} Could not install git automatically"
        echo "Please install git manually and run this script again"
        exit 1
    fi

    echo -e "${GREEN}[OK]${NC} Git installed"
fi

# Проверка существующей директории
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}[WARNING]${NC} Directory '$INSTALL_DIR' already exists"
    echo ""
    read -p "Remove existing directory and continue? [y/N]: " remove_dir

    if [[ "$remove_dir" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        echo -e "${GREEN}[OK]${NC} Removed existing directory"
    else
        echo -e "${BLUE}[INFO]${NC} Using existing directory"
        cd "$INSTALL_DIR"

        # Обновляем репозиторий
        echo ""
        echo "Updating repository..."
        git pull
        echo -e "${GREEN}[OK]${NC} Repository updated"
        echo ""

        # Устанавливаем права на исполнение для скриптов
        echo "Setting script permissions..."
        chmod +x scripts/*.sh
        echo -e "${GREEN}[OK]${NC} Script permissions set"
        echo ""

        # Запускаем setup
        bash scripts/setup.sh
        exit 0
    fi
fi

# Клонируем репозиторий
echo ""
echo "Cloning repository..."
if git clone "$REPO_URL" "$INSTALL_DIR"; then
    echo -e "${GREEN}[OK]${NC} Repository cloned"
else
    echo -e "${RED}[ERROR]${NC} Failed to clone repository"
    exit 1
fi

# Переходим в директорию
cd "$INSTALL_DIR"

# Устанавливаем права на исполнение для скриптов
echo ""
echo "Setting script permissions..."
chmod +x scripts/*.sh
echo -e "${GREEN}[OK]${NC} Script permissions set"

# Запускаем setup wizard
echo ""
echo "Starting setup wizard..."
echo ""
bash scripts/setup.sh
