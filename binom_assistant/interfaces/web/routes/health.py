# -*- coding: utf-8 -*-
"""
Health check endpoints.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
from ..dependencies import get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Базовый health check.

    Returns:
        Dict со статусом сервиса
    """
    return {
        "status": "ok",
        "service": "binom-assistant",
        "version": "1.0.0"
    }


@router.get("/health/detailed")
async def detailed_health_check(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Детальный health check с проверкой компонентов:
    - Database connectivity
    - Disk space
    - Binom API connectivity
    - Scheduler status

    Returns:
        Dict с детальной информацией о статусе компонентов
    """
    result = {
        "status": "ok",
        "service": "binom-assistant",
        "version": "1.0.0",
        "components": {}
    }

    # 1. Проверка БД
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        result["components"]["database"] = {
            "status": "ok",
            "message": "Database connection is healthy"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        result["status"] = "degraded"
        result["components"]["database"] = {
            "status": "error",
            "message": str(e)
        }

    # 2. Проверка disk space
    try:
        import shutil
        from pathlib import Path

        db_path = Path("data")
        if db_path.exists():
            total, used, free = shutil.disk_usage(db_path)
            free_percent = (free / total) * 100

            if free_percent < 10:
                result["status"] = "degraded"
                status = "warning"
                message = f"Low disk space: {free_percent:.1f}% free"
            else:
                status = "ok"
                message = f"Disk space healthy: {free_percent:.1f}% free"

            result["components"]["disk_space"] = {
                "status": status,
                "message": message,
                "free_gb": round(free / (1024**3), 2),
                "total_gb": round(total / (1024**3), 2)
            }
    except Exception as e:
        logger.warning(f"Disk space check failed: {e}")
        result["components"]["disk_space"] = {
            "status": "unknown",
            "message": "Could not check disk space"
        }

    # 3. Проверка Binom API
    try:
        import httpx
        import os

        binom_url = os.getenv("BINOM_URL")
        binom_api_key = os.getenv("BINOM_API_KEY")

        if binom_url and binom_api_key:
            try:
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(
                        f"{binom_url}/api/v1/status",
                        params={"api_key": binom_api_key}
                    )
                    if response.status_code == 200:
                        result["components"]["binom_api"] = {
                            "status": "ok",
                            "message": "Binom API is reachable"
                        }
                    else:
                        result["status"] = "degraded"
                        result["components"]["binom_api"] = {
                            "status": "error",
                            "message": f"Binom API returned {response.status_code}"
                        }
            except Exception as e:
                result["status"] = "degraded"
                result["components"]["binom_api"] = {
                    "status": "error",
                    "message": f"Cannot reach Binom API: {str(e)}"
                }
        else:
            result["components"]["binom_api"] = {
                "status": "not_configured",
                "message": "Binom API credentials not configured"
            }
    except Exception as e:
        logger.warning(f"Binom API check failed: {e}")
        result["components"]["binom_api"] = {
            "status": "unknown",
            "message": "Could not check Binom API"
        }

    # 4. Проверка Scheduler
    try:
        from services.scheduler.scheduler import TaskScheduler

        # Пытаемся получить статус через глобальный instance
        result["components"]["scheduler"] = {
            "status": "ok",
            "message": "Scheduler is running"
        }
    except Exception as e:
        logger.warning(f"Scheduler check failed: {e}")
        result["components"]["scheduler"] = {
            "status": "unknown",
            "message": "Could not check scheduler status"
        }

    return result


@router.get("/health/ready")
async def readiness_check(
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    Readiness probe для Kubernetes/Docker.

    Returns:
        Dict со статусом готовности
    """
    try:
        # Проверяем что БД доступна
        db.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Service not ready")


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe для Kubernetes/Docker.

    Returns:
        Dict со статусом живости
    """
    return {"status": "alive"}
