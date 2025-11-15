# === Stage 1: Builder - установка зависимостей ===
FROM python:3.10-slim AS builder

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для сборки Python пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements.txt
COPY binom_assistant/requirements.txt .

# Создаем виртуальное окружение и устанавливаем зависимости
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# === Stage 2: Runtime - финальный образ ===
FROM python:3.10-slim

# Метаданные
LABEL maintainer="garik128"
LABEL description="Binom Assistant - AI-powered analytics for Binom campaigns"
LABEL version="1.0.0"

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем runtime зависимости (curl для healthcheck, git для обновлений)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Копируем виртуальное окружение из builder stage
COPY --from=builder /opt/venv /opt/venv

# Активируем виртуальное окружение
ENV PATH="/opt/venv/bin:$PATH"

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BINOM_ASSISTANT_ROOT=/app/binom_assistant

# Копируем код приложения
COPY binom_assistant/ /app/binom_assistant/

# Копируем файл VERSION
COPY VERSION /app/VERSION

# Копируем скрипты
COPY scripts/ /app/scripts/

# Делаем скрипты исполняемыми
RUN chmod +x /app/scripts/*.sh

# Создаем директории для данных, логов и бэкапов
RUN mkdir -p /app/data /app/logs /app/backups && \
    chmod 755 /app/data /app/logs /app/backups

# Expose порт приложения
EXPOSE 8000

# Healthcheck - проверяем что приложение отвечает
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD /app/scripts/healthcheck.sh

# Entrypoint для инициализации (миграции БД)
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Команда запуска приложения
CMD ["python", "/app/binom_assistant/run_web.py"]
