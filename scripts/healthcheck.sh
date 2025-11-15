#!/bin/bash
# Health check скрипт для Docker HEALTHCHECK
# Проверяет что FastAPI приложение отвечает на /api/v1/health endpoint

curl -f http://localhost:8000/api/v1/health || exit 1
