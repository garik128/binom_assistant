#!/bin/bash
set -e

# Цвета для вывода (ANSI коды, БЕЗ ЭМОДЗИ!)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
SETUP_CONFIG=".setup_config"
DOCKER_IMAGE="ghcr.io/garik128/binom_assistant:latest"
LOG_FILE="/tmp/binom-assistant-install-$(date +%Y%m%d-%H%M%S).log"

# Глобальные переменные для сохранения данных пользователя
MODE=""
DOMAIN=""
SUBPATH=""
PANEL="none"
SERVER_IP=""
NGINX_CONF_DIR=""
NGINX_SITES_ENABLED=""
SSL_CERT_DIR=""
LOG_DIR=""
BINOM_URL=""
BINOM_API_KEY=""
AUTH_USERNAME=""
AUTH_PASSWORD=""
AUTH_JWT_SECRET=""
TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
TELEGRAM_ALERT_BASE_URL=""
OPENROUTER_API_KEY=""

# ============================================================================
# УТИЛИТЫ
# ============================================================================

log() {
    local message="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" | tee -a "$LOG_FILE"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   Binom Assistant Setup Wizard        ${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_phase() {
    local phase_num=$1
    local phase_name=$2
    echo ""
    echo -e "${BLUE}========================================"
    echo -e "  PHASE ${phase_num}: ${phase_name}"
    echo -e "========================================${NC}"
    echo ""
}

generate_secret() {
    if command -v openssl &> /dev/null; then
        openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
    elif command -v python3 &> /dev/null; then
        python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    else
        cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1
    fi
}

set_script_permissions() {
    echo -e "${YELLOW}Setting script permissions...${NC}"

    if [ -d "scripts" ]; then
        chmod +x scripts/*.sh
        echo -e "${GREEN}[OK]${NC} Script permissions set"
    else
        echo -e "${YELLOW}[WARNING]${NC} Scripts directory not found"
    fi

    echo ""
}

detect_server_ip() {
    # Try multiple methods to detect public IP
    local detected_ip=""

    # Method 1: ifconfig.me
    detected_ip=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null)

    # Method 2: ipinfo.io if first failed
    if [ -z "$detected_ip" ]; then
        detected_ip=$(curl -s --connect-timeout 5 ipinfo.io/ip 2>/dev/null)
    fi

    # Method 3: icanhazip.com if still failed
    if [ -z "$detected_ip" ]; then
        detected_ip=$(curl -s --connect-timeout 5 icanhazip.com 2>/dev/null)
    fi

    # Fallback: use hostname -I
    if [ -z "$detected_ip" ]; then
        detected_ip=$(hostname -I | awk '{print $1}')
    fi

    echo "$detected_ip"
}

# ============================================================================
# ФАЗА 1: СБОР ДАННЫХ (Интерактивные вопросы)
# ============================================================================

collect_deployment_mode() {
    echo -e "${YELLOW}[1/8] Select deployment mode${NC}"
    echo "  1) IP:port (no nginx, direct access via IP:8000)"
    echo "  2) Domain (example.com)"
    echo "  3) Subdomain (binom.example.com)"
    echo "  4) Subpath (example.com/binom)"
    echo ""

    while true; do
        read -p "Your choice [1-4]: " choice
        case $choice in
            1) MODE="ip"; break;;
            2) MODE="domain"; break;;
            3) MODE="subdomain"; break;;
            4) MODE="subpath"; break;;
            *) echo -e "${RED}Invalid choice. Please enter 1-4${NC}";;
        esac
    done

    echo -e "${GREEN}[OK]${NC} Selected mode: $MODE"
    echo ""
}

collect_domain() {
    if [ "$MODE" = "ip" ]; then
        DOMAIN="localhost"
        echo -e "${YELLOW}[2/8] Domain configuration${NC}"
        echo -e "${BLUE}[SKIP]${NC} Not required for IP:port mode"
        echo ""
        return
    fi

    echo -e "${YELLOW}[2/8] Domain configuration${NC}"

    if [ "$MODE" = "domain" ]; then
        read -p "Enter your domain (e.g., example.com): " DOMAIN
    elif [ "$MODE" = "subdomain" ]; then
        read -p "Enter your subdomain (e.g., binom.example.com): " DOMAIN
    elif [ "$MODE" = "subpath" ]; then
        read -p "Enter your base domain (e.g., example.com): " DOMAIN

        while [ -z "$DOMAIN" ]; do
            echo -e "${RED}Error: Domain is required${NC}"
            read -p "Enter your base domain: " DOMAIN
        done

        echo ""
        read -p "Enter subpath (e.g., binom): " SUBPATH_INPUT

        # Очищаем от слешей и пробелов
        SUBPATH_INPUT=$(echo "$SUBPATH_INPUT" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/^\///;s/\/$//')

        # Используем /binom по умолчанию если пусто
        if [ -z "$SUBPATH_INPUT" ]; then
            SUBPATH="/binom"
            echo -e "${BLUE}[INFO]${NC} Using default subpath: $SUBPATH"
        else
            SUBPATH="/$SUBPATH_INPUT"
        fi
    fi

    while [ -z "$DOMAIN" ]; do
        echo -e "${RED}Error: Domain is required${NC}"
        read -p "Enter your domain: " DOMAIN
    done

    echo -e "${GREEN}[OK]${NC} Domain: $DOMAIN"
    if [ -n "$SUBPATH" ]; then
        echo -e "${GREEN}[OK]${NC} Subpath: $SUBPATH"
    fi
    echo ""
}

collect_binom_config() {
    echo -e "${YELLOW}[3/8] Binom configuration${NC}"
    echo ""
    echo "IMPORTANT: Binom API URL must include your unique API file."
    echo "This file name is different for each Binom installation."
    echo ""
    echo "Examples:"
    echo "  http://tracker.example.com/index.php"
    echo "  https://my-tracker.com/index.php"
    echo "  http://123.456.78.9/your_unique_name.php"
    echo ""

    # Binom API URL
    read -p "Enter your full Binom API URL (with .php file): " BINOM_URL
    while [ -z "$BINOM_URL" ]; do
        echo -e "${RED}Error: Binom API URL is required${NC}"
        read -p "Enter your full Binom API URL: " BINOM_URL
    done

    # Validate that URL ends with .php
    if [[ ! "$BINOM_URL" =~ \.php$ ]]; then
        echo -e "${YELLOW}[WARNING]${NC} URL doesn't end with .php"
        read -p "Continue anyway? [y/N]: " continue_anyway
        if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
            collect_binom_config
            return
        fi
    fi

    # Binom API Key
    echo ""
    read -p "Enter your Binom API Key: " BINOM_API_KEY
    while [ -z "$BINOM_API_KEY" ]; do
        echo -e "${RED}Error: Binom API Key is required${NC}"
        read -p "Enter your Binom API Key: " BINOM_API_KEY
    done

    echo -e "${GREEN}[OK]${NC} Binom configuration saved"
    echo ""
}

collect_auth_config() {
    echo -e "${YELLOW}[4/8] Authentication configuration${NC}"
    echo ""

    # Username
    read -p "Enter admin username [admin]: " AUTH_USERNAME
    AUTH_USERNAME=${AUTH_USERNAME:-admin}

    # Password
    read -s -p "Enter admin password: " AUTH_PASSWORD
    echo ""
    while [ -z "$AUTH_PASSWORD" ] || [ "$AUTH_PASSWORD" = "admin" ]; do
        echo -e "${RED}Error: Password cannot be empty or 'admin'${NC}"
        read -s -p "Enter admin password: " AUTH_PASSWORD
        echo ""
    done

    # Generate JWT Secret
    echo "Generating JWT secret..."
    AUTH_JWT_SECRET=$(generate_secret)

    echo -e "${GREEN}[OK]${NC} Admin username: $AUTH_USERNAME"
    echo -e "${GREEN}[OK]${NC} Admin password: ********"
    echo -e "${GREEN}[OK]${NC} JWT secret generated"
    echo ""
}

collect_telegram_config() {
    echo -e "${YELLOW}[5/8] Telegram notifications (optional)${NC}"
    echo ""

    read -p "Configure Telegram notifications? [y/N]: " setup_telegram

    if [[ "$setup_telegram" =~ ^[Yy]$ ]]; then
        read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
        read -p "Enter Telegram Chat ID: " TELEGRAM_CHAT_ID

        # Determine alert base URL
        if [ "$MODE" = "ip" ]; then
            echo "Detecting server IP..."
            SERVER_IP=$(detect_server_ip)
            if [ -n "$SERVER_IP" ]; then
                echo -e "${GREEN}[OK]${NC} Detected server IP: $SERVER_IP"
                TELEGRAM_ALERT_BASE_URL="http://${SERVER_IP}:8000"
            else
                echo -e "${YELLOW}[WARNING]${NC} Could not auto-detect IP"
                read -p "Enter your server IP manually: " SERVER_IP
                TELEGRAM_ALERT_BASE_URL="http://${SERVER_IP}:8000"
            fi
        else
            if [ "$MODE" = "subpath" ]; then
                TELEGRAM_ALERT_BASE_URL="http://${DOMAIN}${SUBPATH}"
            else
                TELEGRAM_ALERT_BASE_URL="http://${DOMAIN}"
            fi
        fi

        echo -e "${GREEN}[OK]${NC} Telegram notifications configured"
    else
        echo -e "${BLUE}[SKIP]${NC} Telegram notifications disabled"
    fi

    echo ""
}

collect_openrouter_config() {
    echo -e "${YELLOW}[6/8] OpenRouter AI (optional)${NC}"
    echo ""

    read -p "Configure OpenRouter AI analysis? [y/N]: " setup_openrouter

    if [[ "$setup_openrouter" =~ ^[Yy]$ ]]; then
        read -p "Enter OpenRouter API Key: " OPENROUTER_API_KEY
        echo -e "${GREEN}[OK]${NC} OpenRouter AI configured"
    else
        echo -e "${BLUE}[SKIP]${NC} OpenRouter AI disabled"
    fi

    echo ""
}

# ============================================================================
# ФАЗА 2: ПРОВЕРКИ (Без интерактивных вопросов)
# ============================================================================

check_requirements() {
    echo -e "${YELLOW}[7/8] Checking system requirements${NC}"

    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}[ERROR]${NC} Docker is not installed"
        echo ""
        echo "Please install Docker first:"
        echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
        echo "  sudo sh get-docker.sh"
        exit 1
    fi

    DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
    echo -e "${GREEN}[OK]${NC} Docker: $DOCKER_VERSION"

    # Проверка Docker Compose
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}[ERROR]${NC} Docker Compose is not installed"
        echo ""
        echo "Please install Docker Compose v2+"
        exit 1
    fi

    COMPOSE_VERSION=$(docker compose version --short)
    echo -e "${GREEN}[OK]${NC} Docker Compose: $COMPOSE_VERSION"

    echo ""
}

check_nginx() {
    if [ "$MODE" = "ip" ]; then
        echo -e "${YELLOW}Checking Nginx...${NC}"
        echo -e "${BLUE}[SKIP]${NC} Nginx not required for IP:port mode"
        echo ""
        return
    fi

    echo -e "${YELLOW}Checking Nginx...${NC}"

    if ! command -v nginx &> /dev/null; then
        echo -e "${YELLOW}[WARNING]${NC} Nginx is not installed"
        echo ""
        read -p "Install Nginx now? [y/N]: " install_nginx

        if [[ "$install_nginx" =~ ^[Yy]$ ]]; then
            echo "Installing Nginx..."
            sudo apt update
            sudo apt install -y nginx
            echo -e "${GREEN}[OK]${NC} Nginx installed"
        else
            echo -e "${RED}[ERROR]${NC} Nginx is required for domain/subdomain/subpath modes"
            exit 1
        fi
    else
        NGINX_VERSION=$(nginx -v 2>&1 | awk '{print $3}')
        echo -e "${GREEN}[OK]${NC} Nginx: $NGINX_VERSION"
    fi

    # Проверка запущен ли nginx
    if systemctl is-active --quiet nginx; then
        echo -e "${GREEN}[OK]${NC} Nginx is running"
    else
        echo -e "${YELLOW}[WARNING]${NC} Nginx is not running"
        sudo systemctl start nginx
        echo -e "${GREEN}[OK]${NC} Nginx started"
    fi

    echo ""
}

detect_panel() {
    echo -e "${YELLOW}Detecting control panel...${NC}"

    # ISPmanager - проверяем правильный путь к mgrctl
    if [ -f "/usr/local/mgr5/sbin/mgrctl" ]; then
        PANEL="ispmanager"
        NGINX_CONF_DIR="/etc/nginx/vhosts"
        NGINX_SITES_ENABLED="/etc/nginx/vhosts"
        SSL_CERT_DIR="/var/www/httpd-cert"
        LOG_DIR="/var/www/httpd-logs"

        # Определяем IP адрес сервера для ISPmanager
        echo -e "${YELLOW}Detecting server IP address...${NC}"
        SERVER_IP=$(detect_server_ip)

        if [ -z "$SERVER_IP" ]; then
            echo -e "${YELLOW}[WARNING]${NC} Could not auto-detect server IP"
            read -p "Please enter server IP address manually: " SERVER_IP
            while [ -z "$SERVER_IP" ]; do
                echo -e "${RED}Error: IP address is required for ISPmanager${NC}"
                read -p "Please enter server IP address: " SERVER_IP
            done
        fi

        echo -e "${GREEN}[OK]${NC} Detected: ISPmanager"
        echo -e "${GREEN}[OK]${NC} Server IP: $SERVER_IP"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"
        log "[INFO] ISPmanager detected, server IP: $SERVER_IP"

    # FastPanel
    elif [ -d "/usr/local/fastpanel" ] || [ -f "/usr/bin/fastpanel" ]; then
        PANEL="fastpanel"
        NGINX_CONF_DIR="/etc/nginx/sites-available"
        NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
        SSL_CERT_DIR="/etc/letsencrypt/live"
        LOG_DIR="/var/log/nginx"
        echo -e "${GREEN}[OK]${NC} Detected: FastPanel"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"

    # Plesk
    elif [ -d "/usr/local/psa" ] || command -v plesk &> /dev/null; then
        PANEL="plesk"
        NGINX_CONF_DIR="/etc/nginx/plesk.conf.d/vhosts"
        NGINX_SITES_ENABLED="/etc/nginx/plesk.conf.d/vhosts"
        SSL_CERT_DIR="/etc/letsencrypt/live"
        LOG_DIR="/var/log/plesk-nginx"
        echo -e "${GREEN}[OK]${NC} Detected: Plesk"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"

    # VestaCP / HestiaCP
    elif [ -d "/usr/local/vesta" ] || [ -d "/usr/local/hestia" ]; then
        if [ -d "/usr/local/hestia" ]; then
            PANEL="hestiacp"
            echo -e "${GREEN}[OK]${NC} Detected: HestiaCP"
        else
            PANEL="vestacp"
            echo -e "${GREEN}[OK]${NC} Detected: VestaCP"
        fi
        NGINX_CONF_DIR="/etc/nginx/conf.d"
        NGINX_SITES_ENABLED="/etc/nginx/conf.d"
        SSL_CERT_DIR="/usr/local/${PANEL}/ssl"
        LOG_DIR="/var/log/nginx/domains"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"

    # CyberPanel
    elif [ -d "/usr/local/CyberCP" ]; then
        PANEL="cyberpanel"
        NGINX_CONF_DIR="/etc/nginx/sites-available"
        NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
        SSL_CERT_DIR="/etc/letsencrypt/live"
        LOG_DIR="/home/cyberpanel"
        echo -e "${GREEN}[OK]${NC} Detected: CyberPanel"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"

    # No panel - стандартный nginx
    else
        PANEL="none"
        NGINX_CONF_DIR="/etc/nginx/sites-available"
        NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
        SSL_CERT_DIR="/etc/letsencrypt/live"
        LOG_DIR="/var/log/nginx"
        echo -e "${BLUE}[INFO]${NC} No control panel detected (standard nginx)"
        echo -e "${BLUE}[INFO]${NC} Nginx config dir: $NGINX_CONF_DIR"
    fi

    echo ""
}

check_port_available() {
    echo -e "${YELLOW}Checking port 8000...${NC}"

    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}[WARNING]${NC} Port 8000 is already in use"
        echo ""
        echo "Process using port 8000:"
        lsof -i :8000
        echo ""
        read -p "Stop existing process and continue? [y/N]: " stop_process

        if [[ "$stop_process" =~ ^[Yy]$ ]]; then
            PID=$(lsof -ti :8000)
            sudo kill -9 $PID
            echo -e "${GREEN}[OK]${NC} Process stopped"
        else
            echo -e "${RED}[ERROR]${NC} Port 8000 must be free"
            exit 1
        fi
    else
        echo -e "${GREEN}[OK]${NC} Port 8000 is available"
    fi

    echo ""
}

backup_file() {
    local file=$1
    if [ -f "$file" ]; then
        local backup="${file}.backup-$(date +%Y%m%d-%H%M%S)"
        sudo cp "$file" "$backup"
        echo -e "${GREEN}[OK]${NC} Backup created: $backup"
        return 0
    fi
    return 1
}

check_existing_configs() {
    if [ "$MODE" = "ip" ]; then
        return
    fi

    echo -e "${YELLOW}Checking existing configurations...${NC}"

    # Ищем конфиги по домену во всех возможных местах
    local EXISTING_CONFIGS=$(find /etc/nginx -name "*${DOMAIN}*" -type f 2>/dev/null)

    if [ -n "$EXISTING_CONFIGS" ]; then
        echo -e "${YELLOW}[WARNING]${NC} Found existing nginx configs for domain ${DOMAIN}:"
        echo ""
        echo "$EXISTING_CONFIGS"
        echo ""
        echo "Choose action:"
        echo "  1) Backup and replace (recommended)"
        echo "  2) Cancel installation"
        read -p "Your choice [1-2]: " choice

        case $choice in
            1)
                echo ""
                echo "Creating backups..."
                for conf in $EXISTING_CONFIGS; do
                    backup_file "$conf"
                done
                echo -e "${GREEN}[OK]${NC} Backups created"
                ;;
            2)
                echo -e "${RED}[CANCELLED]${NC} Installation cancelled"
                echo ""
                echo "Please configure nginx manually using examples in nginx/examples/"
                exit 0
                ;;
            *)
                echo -e "${RED}[ERROR]${NC} Invalid choice"
                exit 1
                ;;
        esac
    fi

    echo -e "${GREEN}[OK]${NC} Ready to proceed"
    echo ""
}

# ============================================================================
# ФАЗА 3: УСТАНОВКА (Автоматически, без вопросов)
# ============================================================================

create_env_file() {
    echo -e "${YELLOW}[8/8] Creating .env configuration${NC}"

    if [ ! -f "binom_assistant/.env.example" ]; then
        echo -e "${RED}[ERROR]${NC} .env.example not found"
        exit 1
    fi

    # Копируем пример
    cp binom_assistant/.env.example binom_assistant/.env

    # Применяем значения
    sed -i "s|^BINOM_URL=.*|BINOM_URL=$BINOM_URL|" binom_assistant/.env
    sed -i "s|^BINOM_API_KEY=.*|BINOM_API_KEY=$BINOM_API_KEY|" binom_assistant/.env
    sed -i "s|^AUTH_USERNAME=.*|AUTH_USERNAME=$AUTH_USERNAME|" binom_assistant/.env
    sed -i "s|^AUTH_PASSWORD=.*|AUTH_PASSWORD=$AUTH_PASSWORD|" binom_assistant/.env
    sed -i "s|^AUTH_JWT_SECRET=.*|AUTH_JWT_SECRET=$AUTH_JWT_SECRET|" binom_assistant/.env

    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        # Очищаем значения от возможных префиксов (защита от повторного запуска)
        TELEGRAM_BOT_TOKEN_CLEAN=$(echo "$TELEGRAM_BOT_TOKEN" | sed 's/^.*=//')
        TELEGRAM_CHAT_ID_CLEAN=$(echo "$TELEGRAM_CHAT_ID" | sed 's/^.*=//')
        TELEGRAM_ALERT_BASE_URL_CLEAN=$(echo "$TELEGRAM_ALERT_BASE_URL" | sed 's/^.*=//')

        sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN_CLEAN|" binom_assistant/.env
        sed -i "s|^TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID_CLEAN|" binom_assistant/.env
        sed -i "s|^TELEGRAM_ALERT_BASE_URL=.*|TELEGRAM_ALERT_BASE_URL=$TELEGRAM_ALERT_BASE_URL_CLEAN|" binom_assistant/.env
    fi

    if [ -n "$OPENROUTER_API_KEY" ]; then
        sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$OPENROUTER_API_KEY|" binom_assistant/.env
    fi

    echo -e "${GREEN}[OK]${NC} Configuration file created"
    echo ""
}

generate_nginx_config() {
    if [ "$MODE" = "ip" ]; then
        log "[INFO] Configuring Nginx - skipped for IP:port mode"
        echo -e "${YELLOW}Configuring Nginx...${NC}"
        echo -e "${BLUE}[SKIP]${NC} Not required for IP:port mode"
        echo ""
        return
    fi

    log "[INFO] Configuring Nginx for mode: $MODE, domain: $DOMAIN, panel: $PANEL"
    echo -e "${YELLOW}Configuring Nginx...${NC}"

    # Обработка режима Subpath - добавляем location block в существующий конфиг
    if [ "$MODE" = "subpath" ]; then
        log "[INFO] Subpath mode - searching for existing config for domain: $DOMAIN"

        # Ищем конфиг для базового домена
        local EXISTING_CONF=$(find /etc/nginx -name "*${DOMAIN}*.conf" -o -name "*${DOMAIN}" | grep -v backup | head -1)

        if [ -z "$EXISTING_CONF" ]; then
            echo -e "${RED}[ERROR]${NC} No nginx config found for domain: $DOMAIN"
            echo ""
            echo "For subpath mode, you need an existing nginx config for the base domain."
            echo "Please create the domain first in your panel, then run this installer again."
            log "[ERROR] No nginx config found for domain: $DOMAIN"
            exit 1
        fi

        log "[INFO] Found existing config: $EXISTING_CONF"
        echo -e "${GREEN}[OK]${NC} Found existing config: $EXISTING_CONF"

        # Проверяем нет ли уже location для этого subpath
        if sudo grep -q "location ${SUBPATH}" "$EXISTING_CONF"; then
            echo -e "${RED}[ERROR]${NC} Location ${SUBPATH} already exists in config"
            log "[ERROR] Location ${SUBPATH} already exists"
            exit 1
        fi

        # Создаем backup
        backup_file "$EXISTING_CONF"

        # Создаем временный файл с location block
        local LOCATION_BLOCK=$(cat <<EOF

    # Binom Assistant on subpath ${SUBPATH}
    location ${SUBPATH}/ {
        rewrite ^${SUBPATH}/(.*) /\$1 break;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Prefix ${SUBPATH};

        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        proxy_buffering off;

        client_max_body_size 10M;
    }
EOF
)

        # Добавляем location block перед последней закрывающей скобкой server block
        local TEMP_CONF="/tmp/nginx-binom-temp.conf"
        # Находим последнюю закрывающую скобку и вставляем перед ней
        sudo awk -v location="$LOCATION_BLOCK" '/^}/ && !found {print location; found=1} {print}' "$EXISTING_CONF" > "$TEMP_CONF"
        sudo mv "$TEMP_CONF" "$EXISTING_CONF"

        log "[INFO] Location block added to $EXISTING_CONF"
        echo -e "${GREEN}[OK]${NC} Location block added"

    else
        # Обработка режимов domain и subdomain - создаем отдельный конфиг

        # Определяем путь к конфигу в зависимости от панели
        local CONFIG_PATH
        if [ "$PANEL" = "ispmanager" ]; then
            # ISPmanager использует структуру /etc/nginx/vhosts/DOMAIN/DOMAIN.conf
            # Для поддоменов типа binom.example.com берем базовый домен (example.com)
            local BASE_DOMAIN
            if [ "$MODE" = "subdomain" ]; then
                # Извлекаем базовый домен из поддомена (binom.example.com -> example.com)
                BASE_DOMAIN=$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')
            else
                BASE_DOMAIN="$DOMAIN"
            fi

            sudo mkdir -p "${NGINX_CONF_DIR}/${BASE_DOMAIN}"
            CONFIG_PATH="${NGINX_CONF_DIR}/${BASE_DOMAIN}/${DOMAIN}.conf"
            log "[INFO] ISPmanager: Base domain: $BASE_DOMAIN, Config for: $DOMAIN"
        else
            CONFIG_PATH="${NGINX_CONF_DIR}/binom-assistant.conf"
        fi

        log "[INFO] Config path: $CONFIG_PATH"

        # Для ISPmanager создаем конфиг динамически с привязкой к IP
        if [ "$PANEL" = "ispmanager" ]; then
            log "[INFO] Generating ISPmanager-specific config with IP binding"

            # Определяем пути к SSL сертификатам
            local BASE_DOMAIN_FOR_SSL
            if [ "$MODE" = "subdomain" ]; then
                BASE_DOMAIN_FOR_SSL=$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')
            else
                BASE_DOMAIN_FOR_SSL="$DOMAIN"
            fi

            local SSL_CERT="/var/www/httpd-cert/${BASE_DOMAIN_FOR_SSL}/${DOMAIN}_le1.crt"
            local SSL_KEY="/var/www/httpd-cert/${BASE_DOMAIN_FOR_SSL}/${DOMAIN}_le1.key"

            # Генерируем конфиг для ISPmanager
            sudo tee "$CONFIG_PATH" > /dev/null <<EOF
# Binom Assistant - ISPmanager configuration
# Generated by installer on $(date)

server {
    listen ${SERVER_IP}:80;
    server_name ${DOMAIN} www.${DOMAIN};

    # Redirect to HTTPS (uncomment after SSL setup)
    # return 301 https://\$server_name\$request_uri;
}

server {
    # HTTP port (80) - for initial setup
    listen ${SERVER_IP}:80;

    # HTTPS port (443) - uncomment after SSL certificate setup
    # listen ${SERVER_IP}:443 ssl;

    server_name ${DOMAIN} www.${DOMAIN};

    # SSL certificates (uncomment and configure after getting SSL)
    # ssl_certificate ${SSL_CERT};
    # ssl_certificate_key ${SSL_KEY};
    # ssl_protocols TLSv1.2 TLSv1.3;
    # ssl_ciphers HIGH:!aNULL:!MD5;
    # ssl_prefer_server_ciphers on;
    # ssl_dhparam /etc/ssl/certs/dhparam4096.pem;

    # Logs
    access_log ${LOG_DIR}/${DOMAIN}.access.log;
    error_log ${LOG_DIR}/${DOMAIN}.error.log;

    # Max upload size
    client_max_body_size 10M;

    # Proxy to Docker container
    location / {
        proxy_pass http://127.0.0.1:8000;

        # Headers
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering off;
    }
}
EOF

            log "[INFO] ISPmanager config created with IP binding: ${SERVER_IP}"
            echo -e "${GREEN}[OK]${NC} Config created: $CONFIG_PATH"
            echo -e "${BLUE}[INFO]${NC} IP binding: ${SERVER_IP}:80"
            echo ""
            echo -e "${YELLOW}[NOTE]${NC} SSL paths in config (uncomment after SSL setup):"
            echo "  Certificate: ${SSL_CERT}"
            echo "  Key: ${SSL_KEY}"

        else
            # Для остальных панелей используем шаблоны
            case $MODE in
                domain) TEMPLATE="nginx/examples/domain.conf.example";;
                subdomain) TEMPLATE="nginx/examples/subdomain.conf.example";;
            esac

            if [ ! -f "$TEMPLATE" ]; then
                echo -e "${RED}[ERROR]${NC} Template not found: $TEMPLATE"
                log "[ERROR] Template not found: $TEMPLATE"
                exit 1
            fi

            log "[INFO] Using template: $TEMPLATE"

            # Копируем шаблон
            sudo cp "$TEMPLATE" "$CONFIG_PATH"

            # Заменяем домен в правильном порядке
            if [ "$MODE" = "subdomain" ]; then
                sudo sed -i "s/binom\.example\.com/$DOMAIN/g" "$CONFIG_PATH"
            else
                sudo sed -i "s/example\.com/$DOMAIN/g" "$CONFIG_PATH"
            fi

            # Заменяем пути к логам
            sudo sed -i "s|/var/log/nginx|$LOG_DIR|g" "$CONFIG_PATH"

            log "[INFO] Config created at: $CONFIG_PATH"
            echo -e "${GREEN}[OK]${NC} Config created: $CONFIG_PATH"

            # Создаем symlink только если нужно (не для ISPmanager, Plesk, VestaCP/HestiaCP)
            if [ "$NGINX_SITES_ENABLED" != "$NGINX_CONF_DIR" ]; then
                sudo ln -sf "$CONFIG_PATH" "${NGINX_SITES_ENABLED}/"
                log "[INFO] Symlink created in: $NGINX_SITES_ENABLED"
                echo -e "${GREEN}[OK]${NC} Symlink created"
            fi
        fi
    fi

    # Проверяем синтаксис nginx
    log "[INFO] Testing nginx configuration"
    echo ""
    echo "Testing nginx configuration..."

    if sudo nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        echo ""
        echo -e "${GREEN}[OK]${NC} Nginx configuration is valid"
        log "[INFO] Nginx configuration is valid"

        # Перезагружаем nginx
        sudo systemctl reload nginx
        echo -e "${GREEN}[OK]${NC} Nginx reloaded"
        log "[INFO] Nginx reloaded successfully"
    else
        echo ""
        echo -e "${RED}[ERROR]${NC} Nginx configuration has errors!"
        log "[ERROR] Nginx configuration test failed"

        # Rollback - восстанавливаем из backup
        echo ""
        echo "Rolling back to previous configuration..."
        local BACKUP=$(ls -t "${CONFIG_PATH}.backup-"* 2>/dev/null | head -1)
        if [ -n "$BACKUP" ]; then
            sudo cp "$BACKUP" "$CONFIG_PATH"
            echo -e "${YELLOW}[OK]${NC} Restored from backup: $BACKUP"
            log "[INFO] Restored from backup: $BACKUP"
        fi

        exit 1
    fi

    echo ""
}

pull_docker_image() {
    echo -e "${YELLOW}Pulling Docker image...${NC}"

    if docker compose pull; then
        echo -e "${GREEN}[OK]${NC} Docker image pulled"
    else
        echo -e "${RED}[ERROR]${NC} Failed to pull Docker image"
        exit 1
    fi

    echo ""
}

create_directories() {
    echo -e "${YELLOW}Creating directories...${NC}"

    mkdir -p data logs backups
    chmod 755 data logs backups

    echo -e "${GREEN}[OK]${NC} Directories created"
    echo ""
}

configure_docker_ports() {
    echo -e "${YELLOW}Configuring Docker ports...${NC}"
    log "[INFO] Configuring ports for mode: $MODE"

    # Для режима IP:port оставляем 0.0.0.0 (доступно снаружи)
    # Для режимов с nginx меняем на 127.0.0.1 (только localhost)
    if [ "$MODE" != "ip" ]; then
        # Проверяем текущее значение
        CURRENT_PORT=$(grep -oP '^\s*-\s*"\K[^"]+(?=")' docker-compose.yml | grep ":8000:8000" || echo "not found")
        log "[INFO] Current port binding: $CURRENT_PORT"

        # Меняем на localhost (безопасно для nginx режимов)
        if grep -q "0\.0\.0\.0:8000:8000" docker-compose.yml; then
            sed -i.bak 's/0\.0\.0\.0:8000:8000/127.0.0.1:8000:8000/' docker-compose.yml
            rm -f docker-compose.yml.bak

            # Проверяем что замена прошла успешно
            if grep -q "127\.0\.0\.1:8000:8000" docker-compose.yml; then
                echo -e "${GREEN}[OK]${NC} Port binding: 127.0.0.1:8000 (localhost only)"
                log "[INFO] Port binding changed to 127.0.0.1:8000"
            else
                echo -e "${RED}[WARNING]${NC} Failed to change port binding automatically"
                echo -e "${YELLOW}[INFO]${NC} Port remains: 0.0.0.0:8000 (publicly accessible)"
                log "[WARNING] Failed to change port binding in docker-compose.yml"
                echo ""
                echo "This is a security concern for production. With nginx, port should be 127.0.0.1:8000"
                echo "You can change it manually after installation in docker-compose.yml"
                echo ""
                read -p "Continue with current port settings? [y/N]: " continue_anyway
                if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                    echo -e "${RED}[CANCELLED]${NC} Installation cancelled"
                    log "[INFO] Installation cancelled by user due to port binding issue"
                    exit 1
                fi
                log "[INFO] User chose to continue with 0.0.0.0:8000 binding"
            fi
        else
            echo -e "${BLUE}[INFO]${NC} Port binding already set to localhost"
            log "[INFO] Port already set to localhost or not found"
        fi
    else
        # Режим IP:port - оставляем публичный доступ
        CURRENT_PORT=$(grep -oP '^\s*-\s*"\K[^"]+(?=")' docker-compose.yml | grep ":8000:8000" || echo "0.0.0.0:8000:8000")
        echo -e "${GREEN}[OK]${NC} Port binding: $CURRENT_PORT (publicly accessible)"
        log "[INFO] Port binding kept as $CURRENT_PORT for IP mode"
    fi

    echo ""
}

start_application() {
    echo -e "${YELLOW}Starting application...${NC}"

    if docker compose up -d; then
        echo -e "${GREEN}[OK]${NC} Application started"
    else
        echo -e "${RED}[ERROR]${NC} Failed to start application"
        exit 1
    fi

    echo ""
}

wait_for_health() {
    echo -e "${YELLOW}Waiting for application...${NC}"
    echo "(This may take up to 60 seconds)"
    echo ""

    for i in {1..60}; do
        if curl -sf http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
            echo ""
            echo -e "${GREEN}[OK]${NC} Application is healthy!"
            echo ""
            return 0
        fi
        echo -n "."
        sleep 1
    done

    echo ""
    echo -e "${RED}[WARNING]${NC} Health check timeout"
    echo "Check logs: docker logs binom-assistant"
    echo ""
}

print_summary() {
    log "[INFO] Installation completed successfully"
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}   Установка завершена!                ${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # Информация о конфигурации
    echo "Конфигурация:"
    echo "  Режим развертывания: $MODE"
    if [ "$PANEL" != "none" ]; then
        echo "  Панель управления: $PANEL"
    fi
    echo ""

    if [ "$MODE" = "ip" ]; then
        echo -e "URL доступа: ${GREEN}http://ВАШ_IP_СЕРВЕРА:8000${NC}"
        echo ""
        echo "Замените ВАШ_IP_СЕРВЕРА на фактический IP адрес вашего сервера"
    else
        if [ "$MODE" = "subpath" ]; then
            echo -e "URL доступа: ${GREEN}http://$DOMAIN$SUBPATH${NC}"
        else
            echo -e "URL доступа: ${GREEN}http://$DOMAIN${NC}"
        fi
    fi

    echo ""
    echo "Данные для входа:"
    echo "  Логин:  $AUTH_USERNAME"
    echo "  Пароль: ********"
    echo ""
    echo -e "${RED}ВАЖНО: Смените пароль после первого входа!${NC}"
    echo -e "${YELLOW}После авторизации дождитесь обновления данных${NC}"
    echo ""
    echo "Полезные команды:"
    echo "  Логи:      docker logs -f binom-assistant"
    echo "  Рестарт:   docker compose restart"
    echo "  Стоп:      docker compose down"
    echo "  Обновить:  ./scripts/upgrade.sh"
    echo "  Бэкап:     ./scripts/backup.sh"
    echo ""

    if [ "$MODE" != "ip" ]; then
        echo "Следующие шаги:"

        if [ "$PANEL" = "ispmanager" ]; then
            # Определяем базовый домен для пути
            local BASE_DOMAIN_SUMMARY
            if [ "$MODE" = "subdomain" ]; then
                BASE_DOMAIN_SUMMARY=$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')
            else
                BASE_DOMAIN_SUMMARY="$DOMAIN"
            fi

            echo "  1. Настройте SSL сертификат через ISPmanager:"
            echo "     - Перейдите в панель ISPmanager"
            echo "     - Откройте 'WWW' -> 'WWW-домены' -> Выберите '${DOMAIN}'"
            echo "     - Нажмите 'SSL сертификат' -> 'Let's Encrypt'"
            echo "     - После выпуска SSL отредактируйте nginx конфиг:"
            echo "       ${NGINX_CONF_DIR}/${BASE_DOMAIN_SUMMARY}/${DOMAIN}.conf"
            echo "     - Раскомментируйте строки SSL и редирект на HTTPS"
            echo "     - Перезагрузите nginx: sudo systemctl reload nginx"
        else
            echo "  1. Настройте SSL сертификат (рекомендуется):"
            echo "     sudo certbot --nginx -d $DOMAIN"
        fi
        echo ""
    fi

    echo -e "Лог установки сохранен: ${GREEN}$LOG_FILE${NC}"
    echo ""
}

# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

main() {
    # Инициализируем лог файл
    echo "==================================" > "$LOG_FILE"
    echo "Binom Assistant Installation Log" >> "$LOG_FILE"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
    echo "==================================" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"

    log "[INFO] Starting Binom Assistant installation"
    log "[INFO] Log file: $LOG_FILE"

    print_header

    # ФАЗА 1: Сбор данных (все интерактивные вопросы)
    print_phase 1 "DATA COLLECTION"
    log "[INFO] Phase 1: Data Collection"
    collect_deployment_mode
    collect_domain
    collect_binom_config
    collect_auth_config
    collect_telegram_config
    collect_openrouter_config

    # ФАЗА 2: Проверки (без вопросов, только проверяем)
    print_phase 2 "SYSTEM CHECKS"
    log "[INFO] Phase 2: System Checks"
    check_requirements
    check_nginx
    detect_panel
    check_port_available
    check_existing_configs

    # ФАЗА 3: Установка (автоматически, без вопросов)
    print_phase 3 "INSTALLATION"
    log "[INFO] Phase 3: Installation"
    create_env_file
    create_directories
    set_script_permissions
    generate_nginx_config
    configure_docker_ports
    pull_docker_image
    start_application
    wait_for_health

    # Итог
    print_summary
}

# Запуск
main
