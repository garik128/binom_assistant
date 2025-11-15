# Установка Binom Assistant (Docker)

Полное руководство по установке Binom Assistant на Linux VPS с использованием Docker.

## Требования

### Минимальные требования к серверу:

- **OS:** Linux (рекомендуется Ubuntu 22.04+ или Debian 11+)
- **RAM:** 1 GB минимум, 2 GB рекомендуется
- **Disk:** 5 GB свободного места
- **Docker:** 20.10+
- **Docker Compose:** v2+

### API ключи:

- **Binom API key** (обязательно) - для доступа к вашему Binom трекеру
- **Telegram Bot Token** (опционально) - для уведомлений
- **OpenRouter API key** (опционально) - для AI анализа

---

## Быстрая установка (1 команда)

Автоматический установщик с интерактивным мастером:

```bash
curl -fsSL https://raw.githubusercontent.com/garik128/binom_assistant/main/install.sh -o install.sh && bash install.sh
```

Мастер проведет вас через все шаги:
1. Установка git (если требуется)
2. Клонирование репозитория
3. Проверка Docker и Docker Compose
4. Выбор варианта доступа (IP, домен, поддомен, субпапка)
5. Настройка Nginx (если нужен)
6. Настройка `.env` файла
7. Запуск приложения

---

## Ручная установка (пошагово)

### Шаг 1: Установка Docker

Если Docker еще не установлен:

```bash
# Скачать скрипт установки
curl -fsSL https://get.docker.com -o get-docker.sh

# Установить Docker
sudo sh get-docker.sh

# Добавить текущего пользователя в группу docker
sudo usermod -aG docker $USER

# Перелогиниться для применения изменений
newgrp docker

# Проверить установку
docker --version
docker compose version
```

### Шаг 2: Клонирование репозитория

```bash
# Клонировать репозиторий
git clone https://github.com/garik128/binom_assistant.git
cd binom_assistant
```

### Шаг 3: Настройка .env файла

```bash
# Копировать пример
cp binom_assistant/.env.example binom_assistant/.env

# Редактировать файл
nano binom_assistant/.env
```

**Обязательно настройте:**

```bash
# Binom API (ОБЯЗАТЕЛЬНО)
BINOM_URL=http://your-binom-tracker.com
BINOM_API_KEY=your_api_key_here

# Авторизация (ОБЯЗАТЕЛЬНО изменить!)
AUTH_USERNAME=admin
AUTH_PASSWORD=your_secure_password_here

# JWT Secret (ОБЯЗАТЕЛЬНО сгенерировать!)
# Выполните: python -c "import secrets; print(secrets.token_urlsafe(32))"
AUTH_JWT_SECRET=your_random_secret_here

# Telegram (опционально)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ALERT_BASE_URL=http://your-server-ip:8000

# OpenRouter AI (опционально)
OPENROUTER_API_KEY=sk-or-v1-...
```

### Шаг 4: Выбор варианта доступа

#### Вариант 1: IP:port (без Nginx)

Самый простой вариант для быстрого теста:

```bash
# Изменить порт в docker-compose.yml на публичный
sed -i 's/127.0.0.1:8000:8000/0.0.0.0:8000:8000/g' docker-compose.yml

# Запустить
docker compose up -d

# Проверить статус
docker compose ps
```

Приложение доступно: `http://YOUR_SERVER_IP:8000`

⚠️ **Внимание:** Этот вариант не рекомендуется для продакшена!

---

#### Вариант 2: Домен (example.com)

Требуется: Nginx, домен с A-записью на ваш IP

```bash
# 1. Установить Nginx (если еще не установлен)
sudo apt update
sudo apt install nginx -y

# 2. Скопировать конфиг
sudo cp nginx/examples/domain.conf.example /etc/nginx/sites-available/binom-assistant.conf

# 3. Отредактировать конфиг (заменить example.com на ваш домен)
sudo nano /etc/nginx/sites-available/binom-assistant.conf

# 4. Создать symlink
sudo ln -s /etc/nginx/sites-available/binom-assistant.conf /etc/nginx/sites-enabled/

# 5. Проверить синтаксис
sudo nginx -t

# 6. Перезапустить Nginx
sudo systemctl reload nginx

# 7. Запустить приложение
docker compose up -d
```

Приложение доступно: `http://your-domain.com`

---

#### Вариант 3: Поддомен (binom.example.com)

Требуется: Nginx, поддомен с A-записью на ваш IP

```bash
# 1. Установить Nginx (если еще не установлен)
sudo apt update
sudo apt install nginx -y

# 2. Скопировать конфиг
sudo cp nginx/examples/subdomain.conf.example /etc/nginx/sites-available/binom-assistant.conf

# 3. Отредактировать конфиг (заменить binom.example.com на ваш поддомен)
sudo nano /etc/nginx/sites-available/binom-assistant.conf

# 4. Создать symlink
sudo ln -s /etc/nginx/sites-available/binom-assistant.conf /etc/nginx/sites-enabled/

# 5. Проверить синтаксис
sudo nginx -t

# 6. Перезапустить Nginx
sudo systemctl reload nginx

# 7. Запустить приложение
docker compose up -d
```

Приложение доступно: `http://binom.your-domain.com`

---

#### Вариант 4: Субпапка (example.com/binom)

⚠️ **Требует модификации кода!**

Перед использованием этого варианта нужно добавить `root_path` в FastAPI:

**Способ 1: Через переменную окружения**

Добавьте в `binom_assistant/.env`:
```bash
FASTAPI_ROOT_PATH=/binom
```

**Способ 2: Изменение кода**

В файле `binom_assistant/interfaces/web/main.py` найдите:
```python
app = FastAPI(
    title="Binom Assistant API",
    ...
)
```

И добавьте `root_path`:
```python
app = FastAPI(
    title="Binom Assistant API",
    ...
    root_path="/binom"  # Добавить эту строку
)
```

Затем:

```bash
# 1. Установить Nginx
sudo apt update
sudo apt install nginx -y

# 2. Скопировать конфиг
sudo cp nginx/examples/subpath.conf.example /etc/nginx/sites-available/binom-assistant.conf

# 3. Отредактировать конфиг
sudo nano /etc/nginx/sites-available/binom-assistant.conf

# 4. Создать symlink
sudo ln -s /etc/nginx/sites-available/binom-assistant.conf /etc/nginx/sites-enabled/

# 5. Проверить синтаксис
sudo nginx -t

# 6. Перезапустить Nginx
sudo systemctl reload nginx

# 7. Пересобрать образ с изменениями
docker compose down
docker compose build
docker compose up -d
```

Приложение доступно: `http://your-domain.com/binom`

---

## Настройка SSL (HTTPS)

### Автоматическая настройка через Certbot

```bash
# Установить Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx -y

# Получить сертификат (для домена)
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Получить сертификат (для поддомена)
sudo certbot --nginx -d binom.your-domain.com

# Certbot автоматически настроит Nginx для HTTPS
```

Сертификат будет автоматически обновляться через cron.

### Настройка через ispmanager

1. Зайдите в ispmanager
2. Перейдите в "WWW" → "WWW-домены"
3. Выберите ваш домен
4. Нажмите "SSL сертификат" → "Выпустить Let's Encrypt"
5. Дождитесь выпуска

### Настройка через Fastpanel

1. Зайдите в Fastpanel
2. Перейдите в "Сайты"
3. Выберите ваш домен
4. Нажмите "SSL" → "Let's Encrypt"
5. Нажмите "Получить сертификат"

---

## Первый запуск

### 1. Проверка статуса

```bash
# Проверить что контейнер запущен
docker ps | grep binom-assistant

# Проверить логи
docker logs -f binom-assistant

# Проверить health check
curl http://localhost:8000/api/v1/health
```

### 2. Ожидание инициализации

Первый запуск может занять до 40 секунд:
- Применение миграций БД
- Инициализация модулей
- Запуск планировщика

### 3. Доступ к приложению

Откройте в браузере:
- IP:port: `http://YOUR_IP:8000`
- Домен: `http://your-domain.com` или `https://your-domain.com`
- Поддомен: `http://binom.your-domain.com`
- Субпапка: `http://your-domain.com/binom`

### 4. Вход в систему

Используйте учетные данные из `.env`:
- Username: значение `AUTH_USERNAME` (по умолчанию: `admin`)
- Password: значение `AUTH_PASSWORD` (по умолчанию: `admin`)

⚠️ **ВАЖНО:** Немедленно смените пароль после первого входа!

---

## Проверка установки

```bash
# 1. Проверить статус контейнера
docker compose ps

# Вывод должен показать:
# NAME                IMAGE                                    STATUS
# binom-assistant     ghcr.io/garik128/binom_assistant:latest  Up X minutes (healthy)

# 2. Проверить health check
curl http://localhost:8000/api/v1/health

# Вывод должен быть:
# {"status":"ok","service":"binom-assistant","version":"1.0.0"}

# 3. Проверить что БД создана
ls -lh data/binom_assistant.db

# 4. Проверить логи
tail -f logs/app.log
```

---

## Полезные команды

```bash
# Просмотр логов
docker logs -f binom-assistant

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Остановка с удалением volumes (ВНИМАНИЕ: удалит БД!)
docker compose down -v

# Обновление
./scripts/upgrade.sh

# Бэкап БД
./scripts/backup.sh

# Просмотр ресурсов
docker stats binom-assistant
```

---

## Установка без Docker (не проверено)

### Требования
- Python 3.10+
- Binom API key
- Openrouter API key (опционально, для AI-агента)
- Linux/Windows (разработка на Windows, production на Linux VPS)

### Установка

1. **Клонируйте репозиторий**
```bash
git clone https://github.com/your-username/binom-assistant.git
cd binom-assistant
```

2. **Создайте виртуальное окружение**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. **Установите зависимости**
```bash
cd binom_assistant
pip install -r requirements.txt
```

4. **Настройте конфигурацию**

Создайте файл `.env` в папке `binom_assistant/` (скопируйте `.env.example`):

```bash
cp binom_assistant/.env.example binom_assistant/.env
```

Отредактируйте `.env` и укажите ваши настройки:

```bash
# Binom API
BINOM_URL=https://your-binom-domain.com
BINOM_API_KEY=your_binom_api_key_here

# OpenRouter AI (опционально)
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=openai/gpt-4.1-mini

# Telegram (опционально)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Timezone
TIMEZONE=Europe/Moscow
```

**Примечание:** `config.yaml` берет значения из `.env` через подстановку переменных `${VARIABLE_NAME}`

5. **Запустите приложение**
```bash
cd binom_assistant
python run_web.py
```

Веб-интерфейс будет доступен по адресу: **http://127.0.0.1:8000**

### Первичная загрузка данных

При первом запуске рекомендуется выполнить первичную загрузку данных:

```bash
python dev_collector_cli.py --initial --days 30 --fast
```

Это загрузит данные за последние 30 дней без пауз между запросами (~5-10 минут).

---

## Production развертывание (не проверено)

### С systemd (рекомендуется)

```bash
# 1. Копируйте проект на сервер
scp -r binom_assistant user@server:/opt/

# 2. Создайте service файл
sudo nano /etc/systemd/system/binom-assistant.service
```

```ini
[Unit]
Description=Binom Assistant Web Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/binom_assistant/binom_assistant
Environment="PATH=/opt/binom_assistant/venv/bin"
ExecStart=/opt/binom_assistant/venv/bin/python run_web.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 3. Запустите сервис
sudo systemctl daemon-reload
sudo systemctl enable binom-assistant
sudo systemctl start binom-assistant
sudo systemctl status binom-assistant
```

### С Nginx (reverse proxy)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Следующие шаги

1. [Настройка обновлений](UPGRADE.md)
2. [Решение проблем](TROUBLESHOOTING.md)
3. Ознакомьтесь с [README.md](../README.md) для понимания функционала

---

## Поддержка

- **Issues:** https://github.com/garik128/binom_assistant/issues
- **Documentation:** https://github.com/garik128/binom_assistant
