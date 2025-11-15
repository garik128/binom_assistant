# Обновление Binom Assistant

Руководство по обновлению Binom Assistant на новую версию.

## Автоматическое обновление (рекомендуется)

### Обновление на latest версию

```bash
cd /path/to/binom_assistant
./scripts/upgrade.sh
```

Скрипт автоматически:
1. Проверит текущую версию
2. Обновит код из Git (git stash + git pull)
3. Создаст бэкап базы данных в ./backups
4. Сохранит текущий образ для возможности отката
5. Скачает новую версию Docker образа
6. Перезапустит контейнер
7. Проверит healthcheck
8. Покажет новую версию и путь к бэкапу
9. Восстановит локальные изменения из stash
10. В случае ошибки предложит откат

### Обновление на конкретную версию

```bash
./scripts/upgrade.sh v1.2.0
```

---

## Ручное обновление

### Шаг 1: Обновление кода из Git

```bash
# Сохранить локальные изменения
git stash

# Получить обновления
git pull

# Восстановить локальные изменения (если нужно)
git stash pop
```

### Шаг 2: Создание бэкапа

```bash
# Автоматический бэкап
./scripts/backup.sh

# Или вручную
docker compose down
mkdir -p backups
cp data/binom_assistant.db backups/binom_assistant_$(date +%Y-%m-%d_%H-%M-%S).db
docker compose up -d
```

### Шаг 3: Скачивание новой версии

```bash
# Для latest версии
docker compose pull
```

### Шаг 4: Перезапуск

```bash
docker compose up -d
```

### Шаг 5: Проверка логов

```bash
# Следить за логами
docker logs -f binom-assistant

# Проверить healthcheck
curl http://localhost:8000/api/v1/health
```

---

## Откат на предыдущую версию

### Если обновление прошло с ошибкой:

```bash
# 1. Остановить контейнер
docker compose down

# 2. Откатить образ (если использовали upgrade.sh)
docker tag ghcr.io/garik128/binom_assistant:backup-before-upgrade ghcr.io/garik128/binom_assistant:latest

# 3. Запустить
docker compose up -d
```

### Если нужно восстановить БД:

```bash
# 1. Остановить контейнер
docker compose down

# 2. Восстановить БД из бэкапа
gunzip -c backups/binom_assistant_YYYY-MM-DD_HH-MM-SS.db.gz > data/binom_assistant.db

# 3. Запустить
docker compose up -d
```

---

## Миграции базы данных

Миграции применяются автоматически при запуске контейнера (в `entrypoint.sh`).

### Проверка текущей версии БД

```bash
docker exec binom-assistant python -c "
from binom_assistant.storage.database import get_db
db = next(get_db())
# Здесь можно добавить проверку версии БД
print('Database is OK')
"
```

### Ручной запуск миграций (если нужно)

```bash
# Если используется Alembic
docker exec -it binom-assistant bash
cd /app/binom_assistant/storage/database
alembic upgrade head
```

---

## Проверка версии приложения

### Через API

```bash
curl http://localhost:8000/api/v1/health
```

Ответ:
```json
{
  "status": "ok",
  "service": "binom-assistant",
  "version": "1.0.0"
}
```

### Через Docker

```bash
# Проверить тег образа
docker inspect binom-assistant --format='{{.Config.Image}}'

# Вывод: ghcr.io/garik128/binom_assistant:v1.2.0
```

---

## Обновление с сохранением данных

Docker volumes автоматически сохраняют данные между обновлениями:

- `./data/` - SQLite база данных
- `./logs/` - Логи приложения

При выполнении `docker compose down` эти данные **НЕ удаляются**.

⚠️ **ВНИМАНИЕ:** Команда `docker compose down -v` удалит volumes вместе с данными!

---

## Частота обновлений

### Автоматические обновления (опционально)

Можно настроить cron для автоматической проверки обновлений:

```bash
# Редактировать crontab
crontab -e

# Добавить строку (проверка каждую неделю, воскресенье в 3:00)
0 3 * * 0 cd /path/to/binom_assistant && ./scripts/upgrade.sh >> /var/log/binom-upgrade.log 2>&1
```

⚠️ **Не рекомендуется** для критичных систем без предварительного тестирования!

### Мониторинг новых версий

Следите за релизами на GitHub:
- https://github.com/garik128/binom_assistant/releases

Подпишитесь на уведомления:
- Watch → Custom → Releases

---

## Изменения в конфигурации

### При обновлении проверьте:

1. **Файл `.env`** - могут появиться новые переменные
   ```bash
   # Сравните с новой версией
   diff binom_assistant/.env binom_assistant/.env.example
   ```

2. **Nginx конфиги** - могут понадобиться изменения
   ```bash
   # Проверьте примеры в nginx/examples/
   ls -l nginx/examples/
   ```

3. **docker-compose.yml** - могут быть новые настройки
   ```bash
   # Если вы вносили изменения, проверьте совместимость
   git diff docker-compose.yml
   ```

---

## Breaking Changes (Критические изменения)

Критические изменения, требующие вмешательства, описываются в:
- Changelog: https://github.com/garik128/binom_assistant/releases
- Release notes для конкретной версии

### Пример обновления с breaking changes:

Если в новой версии изменилась структура БД или конфигурации:

```bash
# 1. Прочитать Release Notes
# https://github.com/garik128/binom_assistant/releases/tag/v2.0.0

# 2. Создать полный бэкап
./scripts/backup.sh
cp -r data/ data_backup_v1/
cp -r logs/ logs_backup_v1/
cp binom_assistant/.env binom_assistant/.env.v1

# 3. Обновить
./scripts/upgrade.sh v2.0.0

# 4. Проверить что все работает
curl http://localhost:8000/api/v1/health
docker logs binom-assistant

# 5. Если проблемы - откатить (см. выше)
```

---

## Troubleshooting при обновлении

### Проблема: Обновление зависло

```bash
# Остановить все процессы
docker compose down

# Принудительно удалить старый контейнер
docker rm -f binom-assistant

# Запустить заново
docker compose up -d
```

### Проблема: Health check fail после обновления

```bash
# Проверить логи
docker logs binom-assistant

# Возможные причины:
# - Миграции не применились
# - Ошибка в .env файле
# - Несовместимая версия БД

# Решение: откат + проверка логов
```

### Проблема: "bad interpreter: /bin/bash^M" при запуске скриптов

Это проблема с line endings (CRLF вместо LF).

```bash
# Исправить все shell скрипты
find scripts -name "*.sh" -exec sed -i 's/\r$//' {} \;
chmod +x scripts/*.sh

# Или используя dos2unix (если установлен)
find scripts -name "*.sh" -exec dos2unix {} \;
chmod +x scripts/*.sh

# После git pull всегда проверяйте line endings
git pull
git checkout HEAD -- scripts/*.sh
chmod +x scripts/*.sh
```

**Причина:** Файлы были клонированы на Windows с `core.autocrlf=true` и затем перенесены на Linux.

**Решение навсегда:** Файл `.gitattributes` теперь контролирует line endings автоматически.

### Проблема: Потерялись данные

```bash
# Проверить что volume на месте
docker volume ls | grep binom

# Проверить данные
ls -lh data/
ls -lh logs/

# Если данные есть, но приложение их не видит:
# Проверьте пути в docker-compose.yml
```

### Проблема: CSS/JS не обновились после обновления

Если после `git pull` и `upgrade.sh` видишь старые стили:

```bash
# 1. Проверить что файлы обновились на хосте
ls -lh binom_assistant/interfaces/web/static/css/

# 2. Проверить что файлы обновились в контейнере
docker exec binom-assistant ls -lh /app/binom_assistant/interfaces/web/static/css/

# 3. Сравнить даты модификации
stat binom_assistant/interfaces/web/static/css/main.css
docker exec binom-assistant stat /app/binom_assistant/interfaces/web/static/css/main.css

# 4. Если даты разные - пересоздать контейнер
docker compose up -d --force-recreate

# 5. Очистить кеш браузера (Ctrl+Shift+R или Cmd+Shift+R)

# 6. Если не помогло - проверить что GitHub Actions собрал новый образ
# https://github.com/garik128/binom_assistant/actions

# 7. Проверить что сервер отдает правильный файл
curl -I http://localhost:8000/static/css/main.css
# Смотрим на Last-Modified и Content-Length

# 8. Скачать и сравнить с локальным
curl http://localhost:8000/static/css/main.css > /tmp/server_css.css
diff /tmp/server_css.css binom_assistant/interfaces/web/static/css/main.css
```

**Причины:**
- GitHub Actions еще не собрал новый образ (подожди 5 минут после push)
- Volume mount не обновился (нужен `--force-recreate`)
- Браузер кеширует старую версию (нужен Ctrl+Shift+R)
- Service Worker кеширует старую версию (Settings → Clear Browser Cache)
- Контейнер не перезапустился после git pull

---

## Полезные команды

```bash
# Проверить доступные обновления (вручную)
docker pull ghcr.io/garik128/binom_assistant:latest
docker images | grep binom

# Посмотреть размер образа
docker images ghcr.io/garik128/binom_assistant

# Удалить старые образы (освободить место)
docker image prune -a

# Экспорт/импорт базы данных
sqlite3 data/binom_assistant.db .dump > backup.sql
sqlite3 data/binom_assistant.db < backup.sql
```

---

## Чек-лист перед обновлением production

- [ ] Прочитать Release Notes
- [ ] Создать бэкап БД
- [ ] Проверить свободное место на диске
- [ ] Уведомить пользователей (если нужно)
- [ ] Запланировать время для обновления (low traffic)
- [ ] Подготовить план отката
- [ ] Выполнить обновление на тестовом окружении (если есть)
- [ ] Выполнить обновление на production
- [ ] Проверить healthcheck
- [ ] Проверить основной функционал
- [ ] Мониторить логи 10-15 минут после обновления
