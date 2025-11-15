# Nginx конфигурация для Binom Assistant

Этот каталог содержит примеры конфигурационных файлов Nginx для различных вариантов доступа к Binom Assistant.

## Варианты доступа

### 1. Домен (example.com)
**Файл:** `examples/domain.conf.example`

Приложение доступно напрямую через домен:
- `http://example.com` или `https://example.com`

**Плюсы:**
- Самая простая настройка
- Чистые URL без префиксов

**Минусы:**
- Занимает весь домен

---

### 2. Поддомен (binom.example.com)
**Файл:** `examples/subdomain.conf.example`

Приложение доступно через поддомен:
- `http://binom.example.com` или `https://binom.example.com`

**Плюсы:**
- Чистые URL без префиксов
- Основной домен остается свободным

**Минусы:**
- Требуется настройка DNS для поддомена

---

### 3. Субпапка (example.com/binom)
**Файл:** `examples/subpath.conf.example`

Приложение доступно через субпапку основного домена:
- `http://example.com/binom` или `https://example.com/binom`

**Плюсы:**
- Не требуется дополнительный домен/поддомен
- Можно разместить несколько приложений на одном домене

**Минусы:**
- Требуется изменение в коде FastAPI (добавить `root_path`)
- Более сложная настройка

⚠️ **ВАЖНО:** Для работы варианта с субпапкой нужно изменить код приложения:

В файле `binom_assistant/interfaces/web/main.py` добавьте параметр `root_path`:
```python
app = FastAPI(
    title="Binom Assistant API",
    # ... другие параметры ...
    root_path="/binom"  # Добавить эту строку
)
```

Или установите переменную окружения в `.env`:
```bash
FASTAPI_ROOT_PATH=/binom
```

---

## Пошаговая инструкция по установке

### Шаг 1: Выберите подходящий конфиг

Определитесь с вариантом доступа и скопируйте соответствующий файл:

```bash
# Для домена
sudo cp nginx/examples/domain.conf.example /etc/nginx/sites-available/binom-assistant.conf

# Для поддомена
sudo cp nginx/examples/subdomain.conf.example /etc/nginx/sites-available/binom-assistant.conf

# Для субпапки
sudo cp nginx/examples/subpath.conf.example /etc/nginx/sites-available/binom-assistant.conf
```

### Шаг 2: Отредактируйте конфиг

Откройте файл и замените `example.com` на ваш реальный домен:

```bash
sudo nano /etc/nginx/sites-available/binom-assistant.conf
```

Найдите и замените:
- `example.com` → ваш домен
- `binom.example.com` → ваш поддомен (если используете)

### Шаг 3: Проверьте что Docker контейнер запущен

```bash
docker ps | grep binom-assistant
```

Контейнер должен слушать на `127.0.0.1:8000`.

### Шаг 4: Создайте символическую ссылку

```bash
sudo ln -s /etc/nginx/sites-available/binom-assistant.conf /etc/nginx/sites-enabled/
```

### Шаг 5: Проверьте синтаксис Nginx

```bash
sudo nginx -t
```

Должно вывести:
```
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Шаг 6: Перезапустите Nginx

```bash
sudo systemctl reload nginx
```

Или если нужен полный перезапуск:
```bash
sudo systemctl restart nginx
```

### Шаг 7: Проверьте доступность

Откройте в браузере:
- Для домена: `http://your-domain.com`
- Для поддомена: `http://binom.your-domain.com`
- Для субпапки: `http://your-domain.com/binom`

---

## Настройка SSL (HTTPS)

### Вариант 1: Через ispmanager

1. Зайдите в ispmanager
2. Перейдите в "WWW" → "WWW-домены"
3. Выберите ваш домен
4. Нажмите "SSL сертификат" → "Выпустить Let's Encrypt"
5. Дождитесь выпуска сертификата

ispmanager автоматически настроит Nginx для HTTPS.

### Вариант 2: Через Fastpanel

1. Зайдите в Fastpanel
2. Перейдите в "Сайты"
3. Выберите ваш домен
4. Нажмите "SSL" → "Let's Encrypt"
5. Нажмите "Получить сертификат"

Fastpanel автоматически настроит Nginx для HTTPS.

### Вариант 3: Вручную с Certbot

Установите certbot:
```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

Получите сертификат:
```bash
# Для домена
sudo certbot --nginx -d example.com -d www.example.com

# Для поддомена
sudo certbot --nginx -d binom.example.com
```

Certbot автоматически изменит конфигурацию Nginx и настроит HTTPS.

### Проверка автообновления сертификата

Certbot создает cronjob для автообновления. Проверьте:
```bash
sudo systemctl status certbot.timer
```

---

## Troubleshooting (Частые проблемы)

### 1. 502 Bad Gateway

**Причина:** Nginx не может подключиться к Docker контейнеру.

**Решение:**
```bash
# Проверьте что контейнер запущен
docker ps | grep binom-assistant

# Проверьте что приложение слушает на :8000
curl http://127.0.0.1:8000/api/v1/health

# Проверьте логи контейнера
docker logs binom-assistant
```

### 2. 404 Not Found при доступе к /binom

**Причина:** Неправильная настройка субпапки или FastAPI не знает про `root_path`.

**Решение:**
- Убедитесь что в конфиге есть `rewrite ^/binom/(.*) /$1 break;`
- Добавьте `root_path="/binom"` в FastAPI app (см. выше)

### 3. Не работают статические файлы (CSS, JS)

**Причина:** Неправильные пути к статическим файлам.

**Решение для субпапки:**
- Убедитесь что `location /binom/static/` правильно настроен
- Проверьте что FastAPI возвращает правильные пути (с учетом `root_path`)

### 4. SSL сертификат не применяется

**Причина:** Неправильные пути к сертификатам или порт 443 не слушается.

**Решение:**
```bash
# Проверьте что порты 80 и 443 открыты
sudo netstat -tlnp | grep nginx

# Проверьте пути к сертификатам
sudo ls -la /etc/letsencrypt/live/your-domain.com/

# Проверьте синтаксис
sudo nginx -t
```

### 5. Nginx не перезапускается

**Причина:** Синтаксическая ошибка в конфиге.

**Решение:**
```bash
# Проверьте синтаксис
sudo nginx -t

# Посмотрите логи ошибок
sudo tail -f /var/log/nginx/error.log
```

---

## Дополнительные настройки

### Rate Limiting (ограничение запросов)

Добавьте в блок `http` в `/etc/nginx/nginx.conf`:

```nginx
limit_req_zone $binary_remote_addr zone=binom_limit:10m rate=10r/s;
```

И в блок `location /`:

```nginx
limit_req zone=binom_limit burst=20 nodelay;
```

### Кэширование статических файлов

Раскомментируйте в конфиге блок:

```nginx
location /static/ {
    alias /path/to/binom_assistant/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

---

## Полезные команды

```bash
# Проверить статус Nginx
sudo systemctl status nginx

# Перезапустить Nginx
sudo systemctl restart nginx

# Перечитать конфиги (без прерывания соединений)
sudo systemctl reload nginx

# Посмотреть логи Nginx
sudo tail -f /var/log/nginx/binom-assistant-access.log
sudo tail -f /var/log/nginx/binom-assistant-error.log

# Проверить синтаксис конфигов
sudo nginx -t

# Посмотреть активные конфиги
sudo nginx -T
```

---

## Полезные ссылки

- [Nginx документация](https://nginx.org/ru/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Certbot инструкции](https://certbot.eff.org/)
- [FastAPI за прокси](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)
