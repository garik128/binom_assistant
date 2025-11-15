# Решение проблем (Troubleshooting)

Руководство по диагностике и решению частых проблем с Binom Assistant.

---

## Контейнер не запускается

### Симптомы
```bash
docker compose up -d
# Контейнер сразу останавливается
docker ps | grep binom-assistant
# Ничего не найдено
```

### Диагностика

```bash
# Проверить логи
docker logs binom-assistant

# Проверить статус всех контейнеров (включая остановленные)
docker ps -a | grep binom-assistant
```

### Возможные причины и решения

#### 1. Ошибка в .env файле

**Признаки:** В логах `KeyError` или `Config error`

**Решение:**
```bash
# Проверить что .env существует
ls -la binom_assistant/.env

# Сравнить с example
diff binom_assistant/.env binom_assistant/.env.example

# Проверить обязательные поля:
# BINOM_URL, BINOM_API_KEY, AUTH_JWT_SECRET
```

#### 2. Порт 8000 занят

**Признаки:** `bind: address already in use`

**Решение:**
```bash
# Найти процесс на порту 8000
sudo lsof -i :8000

# Убить процесс
sudo kill -9 <PID>

# Или изменить порт в docker-compose.yml
# ports:
#   - "127.0.0.1:8080:8000"  # Вместо 8000
```

#### 3. Ошибка прав доступа

**Признаки:** `Permission denied` в логах

**Решение:**
```bash
# Проверить права на data/ и logs/
ls -la data/ logs/

# Установить правильные права
chmod 755 data/ logs/
chmod 644 data/*.db 2>/dev/null || true
```

#### 4. Недостаточно места на диске

**Признаки:** `no space left on device`

**Решение:**
```bash
# Проверить место
df -h

# Очистить старые Docker образы
docker system prune -a

# Очистить старые логи
rm -f logs/*.log.* 2>/dev/null || true
```

---

## Health check fail

### Симптомы
```bash
docker ps
# STATUS: Up X minutes (unhealthy)

curl http://localhost:8000/api/v1/health
# Connection refused или timeout
```

### Диагностика

```bash
# Проверить логи приложения
docker logs --tail 100 binom-assistant

# Проверить что приложение слушает на порту
docker exec binom-assistant netstat -tlnp | grep 8000

# Проверить health check вручную
docker exec binom-assistant /app/scripts/healthcheck.sh
echo $?  # Должно быть 0
```

### Возможные причины и решения

#### 1. Приложение еще инициализируется

**Признаки:** Контейнер запущен меньше 40 секунд

**Решение:** Подождите 40-60 секунд для полной инициализации

#### 2. Ошибка миграций БД

**Признаки:** В логах `alembic` или `migration error`

**Решение:**
```bash
# Проверить БД
ls -lh data/binom_assistant.db

# Попробовать применить миграции вручную
docker exec -it binom-assistant bash
cd /app/binom_assistant/storage/database
alembic upgrade head
```

#### 3. Поврежденная БД

**Признаки:** `database disk image is malformed`

**Решение:**
```bash
# Остановить контейнер
docker compose down

# Проверить целостность БД
sqlite3 data/binom_assistant.db "PRAGMA integrity_check;"

# Если БД повреждена - восстановить из бэкапа
gunzip -c backups/latest_backup.db.gz > data/binom_assistant.db

# Запустить
docker compose up -d
```

---

## 502 Bad Gateway (Nginx)

### Симптомы
- При открытии домена в браузере: `502 Bad Gateway`
- Nginx работает, но не может подключиться к приложению

### Диагностика

```bash
# Проверить статус Nginx
sudo systemctl status nginx

# Проверить логи Nginx
sudo tail -f /var/log/nginx/binom-assistant-error.log

# Проверить что контейнер запущен
docker ps | grep binom-assistant

# Проверить что приложение отвечает локально
curl http://127.0.0.1:8000/api/v1/health
```

### Возможные причины и решения

#### 1. Контейнер не запущен

**Решение:**
```bash
docker compose up -d
```

#### 2. Неправильный порт в nginx конфиге

**Признаки:** В логах nginx `connect() failed (111: Connection refused)`

**Решение:**
```bash
# Проверить что в конфиге указан правильный порт
sudo cat /etc/nginx/sites-available/binom-assistant.conf | grep proxy_pass

# Должно быть: proxy_pass http://127.0.0.1:8000;
# Если нет - исправить
sudo nano /etc/nginx/sites-available/binom-assistant.conf

# Проверить синтаксис
sudo nginx -t

# Перезапустить
sudo systemctl reload nginx
```

#### 3. Docker биндит порт только на localhost

**Признаки:** `docker compose ps` показывает `127.0.0.1:8000->8000/tcp`

**Решение:** Это правильная конфигурация! Nginx должен подключаться к `127.0.0.1:8000`.

Если nginx на другом сервере:
```yaml
# В docker-compose.yml изменить
ports:
  - "0.0.0.0:8000:8000"  # Открыть для всех интерфейсов
```

⚠️ Не забудьте про firewall!

#### 4. SELinux блокирует подключение (CentOS/RHEL)

**Признаки:** `permission denied while connecting to upstream`

**Решение:**
```bash
# Разрешить nginx подключаться к localhost
sudo setsebool -P httpd_can_network_connect 1
```

---

## Не работает субпапка (example.com/binom)

### Симптомы
- `example.com` работает, но `example.com/binom` возвращает 404
- Статические файлы (CSS, JS) не загружаются

### Диагностика

```bash
# Проверить логи nginx
sudo tail -f /var/log/nginx/binom-assistant-access.log
sudo tail -f /var/log/nginx/binom-assistant-error.log

# Проверить FastAPI обрабатывает ли root_path
docker exec binom-assistant env | grep ROOT
```

### Решения

#### 1. Добавить root_path в FastAPI

В `.env`:
```bash
FASTAPI_ROOT_PATH=/binom
```

Или в коде `binom_assistant/interfaces/web/main.py`:
```python
app = FastAPI(
    ...
    root_path="/binom"
)
```

#### 2. Проверить nginx rewrite

В конфиге nginx должно быть:
```nginx
location /binom/ {
    rewrite ^/binom/(.*) /$1 break;
    proxy_pass http://127.0.0.1:8000;
    ...
}
```

#### 3. Пересобрать контейнер после изменений

```bash
docker compose down
docker compose build
docker compose up -d
```

---

## SSL сертификат не применяется

### Симптомы
- HTTPS не работает
- Браузер показывает ошибку сертификата

### Диагностика

```bash
# Проверить что nginx слушает 443 порт
sudo netstat -tlnp | grep :443

# Проверить пути к сертификатам
sudo ls -la /etc/letsencrypt/live/your-domain.com/

# Проверить конфиг nginx
sudo nginx -t
```

### Решения

#### 1. Certbot не создал сертификат

```bash
# Запустить certbot заново
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Проверить что домен резолвится
nslookup your-domain.com

# Проверить что порт 80 открыт (нужен для certbot)
sudo ufw status | grep 80
```

#### 2. Неправильные пути в nginx конфиге

```bash
# Проверить пути
sudo cat /etc/nginx/sites-available/binom-assistant.conf | grep ssl_certificate

# Правильные пути для Let's Encrypt:
# ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
```

#### 3. Firewall блокирует 443 порт

```bash
# Открыть порты
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

---

## Проблемы с БД

### База данных заблокирована

**Симптомы:** `database is locked`

**Решение:**
```bash
# Остановить контейнер
docker compose down

# Подождать 5 секунд
sleep 5

# Запустить заново
docker compose up -d
```

### Миграции не применяются

**Симптомы:** Ошибки связанные с отсутствующими таблицами/колонками

**Решение:**
```bash
# Применить миграции вручную
docker exec -it binom-assistant bash
cd /app/binom_assistant/storage/database

# Проверить текущую версию
alembic current

# Применить все миграции
alembic upgrade head

# Выйти
exit
```

### БД повреждена

**Решение:**
```bash
# 1. Остановить контейнер
docker compose down

# 2. Попытаться починить
sqlite3 data/binom_assistant.db "PRAGMA integrity_check;"

# 3. Если не помогло - восстановить из бэкапа
mv data/binom_assistant.db data/binom_assistant_broken.db
gunzip -c backups/binom_assistant_LATEST.db.gz > data/binom_assistant.db

# 4. Запустить
docker compose up -d
```

---

## Высокое потребление ресурсов

### CPU 100%

**Диагностика:**
```bash
docker stats binom-assistant

# Проверить логи на бесконечные циклы
docker logs binom-assistant | grep -i error
```

**Решение:**
- Проверить что scheduler не запускает задачи слишком часто
- Посмотреть в `.env` значение `COLLECTOR_INTERVAL_HOURS`
- Перезапустить контейнер

### Memory leak (утечка памяти)

**Признаки:** Постепенный рост памяти до исчерпания

**Решение:**
```bash
# Временное решение - перезапуск
docker compose restart

# Долгосрочное решение - ограничить память
# В docker-compose.yml добавить:
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

---

## Логи и отладка

### Включение DEBUG режима

В `.env`:
```bash
DEBUG=True
LOG_LEVEL=DEBUG
```

Перезапустить:
```bash
docker compose restart
```

### Просмотр логов

```bash
# Логи контейнера (stdout)
docker logs -f binom-assistant

# Логи приложения (в файле)
tail -f logs/app.log

# Логи nginx
sudo tail -f /var/log/nginx/binom-assistant-access.log
sudo tail -f /var/log/nginx/binom-assistant-error.log

# Только ошибки
docker logs binom-assistant 2>&1 | grep -i error
```

### Вход в контейнер для отладки

```bash
# Запустить bash в контейнере
docker exec -it binom-assistant bash

# Проверить переменные окружения
env | grep BINOM

# Проверить процессы
ps aux

# Проверить сеть
netstat -tlnp

# Выйти
exit
```

---

## Полная переустановка

Если ничего не помогает:

```bash
# 1. Создать бэкап данных
./scripts/backup.sh
cp -r data/ data_backup/
cp -r logs/ logs_backup/
cp binom_assistant/.env binom_assistant/.env.backup

# 2. Остановить и удалить все
docker compose down -v
docker rmi ghcr.io/garik128/binom_assistant:latest

# 3. Очистить данные
rm -rf data/ logs/

# 4. Заново установить
./scripts/setup.sh

# 5. Восстановить БД из бэкапа (если нужно)
gunzip -c data_backup/binom_assistant_LATEST.db.gz > data/binom_assistant.db

# 6. Запустить
docker compose up -d
```

---

## Получение помощи

Автор сам плохо понимат как оно работает, но можете написать в telegarm (ссылка есть в footer)
