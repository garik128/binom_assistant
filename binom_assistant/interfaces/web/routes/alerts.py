# -*- coding: utf-8 -*-
"""
API endpoints для алертов из модулей
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from ..dependencies import get_db
from ..auth import get_current_user
from storage.database.models import ModuleRun
import logging

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/alerts")
async def get_alerts(
    period: str = Query("7d", description="Период: 1d, 7d, 14d, 30d"),
    severity: Optional[str] = Query(None, description="Фильтр по важности"),
    module_id: Optional[str] = Query(None, description="Фильтр по модулю"),
    limit: int = Query(100, description="Максимум алертов"),
    db: Session = Depends(get_db)
):
    """
    Получить список алертов из истории запусков модулей.

    Query Params:
        period: Период (1d, 7d, 14d, 30d)
        severity: Фильтр по важности (critical, high, medium, low)
        module_id: Фильтр по модулю
        limit: Максимальное количество алертов

    Returns:
        Список алертов с метаданными
    """
    try:
        # Парсим период (включая текущий день)
        days = int(period.replace('d', ''))
        # Устанавливаем начало дня для корректной фильтрации
        date_from = (datetime.now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

        # Получаем последние успешные запуски модулей
        runs_query = db.query(ModuleRun).filter(
            ModuleRun.status == "success",
            ModuleRun.completed_at >= date_from,
            ModuleRun.results.isnot(None)
        )

        # Фильтр по модулю
        if module_id:
            runs_query = runs_query.filter(ModuleRun.module_id == module_id)

        runs = runs_query.order_by(
            ModuleRun.completed_at.desc()
        ).limit(limit * 2).all()  # Берем больше чтобы после фильтрации осталось достаточно

        # Собираем все алерты
        all_alerts = []
        for run in runs:
            results = run.results or {}
            alerts = results.get("alerts", [])

            for alert in alerts:
                # Добавляем метаданные
                alert_item = {
                    **alert,  # все поля алерта (type, severity, message и т.д.)
                    "module_id": run.module_id,
                    "run_id": run.id,
                    "created_at": run.completed_at.isoformat() if run.completed_at else datetime.now().isoformat()
                }
                all_alerts.append(alert_item)

        # Фильтрация по severity
        if severity:
            all_alerts = [a for a in all_alerts if a.get("severity") == severity]

        # Ограничиваем количество
        all_alerts = all_alerts[:limit]

        # Сортировка по severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_alerts.sort(
            key=lambda a: severity_order.get(a.get("severity"), 999)
        )

        # Подсчитываем по типам
        critical_count = sum(1 for a in all_alerts if a.get("severity") == "critical")
        high_count = sum(1 for a in all_alerts if a.get("severity") == "high")
        medium_count = sum(1 for a in all_alerts if a.get("severity") == "medium")

        logger.info(f"Loaded {len(all_alerts)} alerts from {len(runs)} module runs")

        return {
            "alerts": all_alerts,
            "total": len(all_alerts),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/recent")
async def get_recent_alerts(
    limit: int = Query(10, description="Количество алертов"),
    severity_filter: str = Query(None, description="Фильтр по severity: all, important (critical+high), или конкретный уровень"),
    db: Session = Depends(get_db)
):
    """
    Получить последние N алертов для dropdown меню.

    Query Params:
        limit: Максимальное количество алертов (по умолчанию 10)
        severity_filter: all - все алерты, important - только critical+high (по умолчанию для совместимости), или конкретный уровень

    Returns:
        Список последних алертов
    """
    try:
        # Получаем запуски за последний день
        date_from = datetime.now() - timedelta(days=1)

        runs = db.query(ModuleRun).filter(
            ModuleRun.status == "success",
            ModuleRun.completed_at >= date_from,
            ModuleRun.results.isnot(None)
        ).order_by(
            ModuleRun.completed_at.desc()
        ).limit(50).all()  # Берем больше чтобы собрать достаточно алертов

        # Собираем алерты
        all_alerts = []
        for run in runs:
            results = run.results or {}
            alerts = results.get("alerts", [])

            for alert in alerts:
                alert_item = {
                    **alert,
                    "module_id": run.module_id,
                    "run_id": run.id,
                    "created_at": run.completed_at.isoformat() if run.completed_at else datetime.now().isoformat()
                }
                all_alerts.append(alert_item)

        # Фильтруем по severity если задан фильтр
        if severity_filter == "all":
            # Берем все алерты без фильтрации
            filtered_alerts = all_alerts
        elif severity_filter and severity_filter != "important":
            # Фильтруем по конкретному уровню
            filtered_alerts = [a for a in all_alerts if a.get("severity") == severity_filter]
        else:
            # По умолчанию берем только critical и high для notifications (обратная совместимость)
            filtered_alerts = [a for a in all_alerts if a.get("severity") in ["critical", "high"]]

        # Добавляем ошибки из логов (последние 24 часа)
        try:
            from pathlib import Path
            import re

            logger.info("Starting to parse log files for errors...")

            log_files = [
                Path("logs/app.log"),
                Path("logs/collector.log"),
                Path("logs/stat_periods.log")
            ]

            # Blacklist компонентов - не показывать в уведомлениях
            component_blacklist = {
                'asyncio',  # Системные сообщения asyncio
            }

            cutoff_time = datetime.now() - timedelta(hours=24)
            log_errors = []

            for log_file in log_files:
                if not log_file.exists():
                    continue

                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()

                    # Берем последние строки
                    recent_lines = lines[-500:] if len(lines) > 500 else lines

                    for line in recent_lines:
                        line = line.strip()
                        if not line:
                            continue

                        # Проверяем уровень (только ERROR и CRITICAL)
                        is_error = " - ERROR - " in line or " - CRITICAL - " in line
                        if not is_error:
                            continue

                        # Извлекаем timestamp
                        timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                        if not timestamp_match:
                            continue

                        timestamp_str = timestamp_match.group(1)
                        try:
                            log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            continue

                        # Фильтруем по времени
                        if log_time < cutoff_time:
                            continue

                        # Извлекаем компонент и сообщение
                        parts = line.split(" - ", 3)
                        component = parts[1] if len(parts) > 1 else "unknown"
                        level = parts[2] if len(parts) > 2 else "ERROR"
                        message = parts[3] if len(parts) > 3 else line

                        # Фильтруем системные компоненты из blacklist
                        if component in component_blacklist:
                            logger.debug(f"Skipping blacklisted component '{component}': {message[:50]}")
                            continue

                        # Создаем уникальный ID на основе timestamp + message hash
                        error_id = f"log_{log_file.stem}_{timestamp_str.replace(' ', '_').replace(':', '')}_{abs(hash(message)) % 10000}"

                        # Формат совместимый с системой уведомлений
                        error_alert = {
                            "type": "system_error",
                            "severity": "critical" if "CRITICAL" in level else "high",
                            "message": f"{component}: {message[:150]}",
                            "module_id": "system_logs",
                            "run_id": error_id,  # Уникальный ID для localStorage
                            "created_at": log_time.isoformat(),
                            "source": log_file.name,
                            "is_log_error": True  # Маркер что это из логов
                        }

                        log_errors.append(error_alert)

                except Exception as e:
                    logger.error(f"Error parsing {log_file}: {e}")
                    continue

            # Добавляем ошибки из логов к алертам (только если не фильтруем по конкретному уровню)
            if log_errors and severity_filter != "medium" and severity_filter != "info":
                filtered_alerts.extend(log_errors)
                logger.info(f"Added {len(log_errors)} log errors to notifications")

        except Exception as e:
            logger.error(f"Error loading log errors for notifications: {e}")

        # Сортируем все вместе
        severity_order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
        filtered_alerts.sort(key=lambda a: (severity_order.get(a.get("severity"), 999), a.get("created_at", "")), reverse=True)

        logger.info(f"Loaded {len(filtered_alerts)} recent alerts (filter: {severity_filter or 'default'})")

        return {
            "alerts": filtered_alerts[:limit],
            "total": len(filtered_alerts)
        }

    except Exception as e:
        logger.error(f"Error getting recent alerts: {e}", exc_info=True)
        # Возвращаем пустой список вместо ошибки для UI
        return {"alerts": [], "total": 0}


@router.get("/alerts/unread/count")
async def get_unread_count(db: Session = Depends(get_db)):
    """
    Получить количество непрочитанных алертов для badge.

    Returns:
        Количество критичных и важных алертов за последний день
    """
    try:
        # Алерты за последний день
        date_from = datetime.now() - timedelta(days=1)

        runs = db.query(ModuleRun).filter(
            ModuleRun.status == "success",
            ModuleRun.completed_at >= date_from,
            ModuleRun.results.isnot(None)
        ).all()

        # Считаем critical и high алерты
        critical_count = 0
        high_count = 0

        for run in runs:
            results = run.results or {}
            alerts = results.get("alerts", [])

            for alert in alerts:
                severity = alert.get("severity")
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1

        total_count = critical_count + high_count

        logger.info(f"Unread alerts: {total_count} (critical: {critical_count}, high: {high_count})")

        return {
            "count": total_count,
            "critical": critical_count,
            "high": high_count
        }

    except Exception as e:
        logger.error(f"Error getting unread count: {e}", exc_info=True)
        return {"count": 0, "critical": 0, "high": 0}


@router.delete("/alerts/{run_id}")
async def delete_alert(
    run_id: int,
    db: Session = Depends(get_db)
):
    """
    Удалить алерт (удаляет запись из истории модуля).

    Path Params:
        run_id: ID запуска модуля

    Returns:
        Статус удаления
    """
    try:
        run = db.query(ModuleRun).filter(ModuleRun.id == run_id).first()

        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        db.delete(run)
        db.commit()

        logger.info(f"Deleted module run {run_id} (module: {run.module_id})")

        return {
            "status": "ok",
            "message": f"Alert from run {run_id} deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/bulk")
async def delete_all_alerts(
    period: str = Query("7d", description="Период: 1d, 7d, 14d, 30d"),
    severity: Optional[str] = Query(None, description="Фильтр по важности"),
    module_id: Optional[str] = Query(None, description="Фильтр по модулю"),
    db: Session = Depends(get_db)
):
    """
    Удалить все алерты по фильтрам.

    Query Params:
        period: Период (1d, 7d, 14d, 30d)
        severity: Фильтр по важности (critical, high, medium, low)
        module_id: Фильтр по модулю

    Returns:
        Количество удаленных алертов
    """
    try:
        # Парсим период
        days = int(period.replace('d', ''))
        date_from = datetime.now() - timedelta(days=days - 1)

        # Получаем запуски модулей по фильтрам
        runs_query = db.query(ModuleRun).filter(
            ModuleRun.status == "success",
            ModuleRun.completed_at >= date_from,
            ModuleRun.results.isnot(None)
        )

        # Фильтр по модулю
        if module_id:
            runs_query = runs_query.filter(ModuleRun.module_id == module_id)

        runs = runs_query.all()

        # Собираем ID runs с нужными алертами
        runs_to_delete = []
        for run in runs:
            results = run.results or {}
            alerts = results.get("alerts", [])

            # Если есть фильтр по severity, проверяем
            if severity:
                has_matching_alert = any(a.get("severity") == severity for a in alerts)
                if has_matching_alert:
                    runs_to_delete.append(run.id)
            else:
                # Без фильтра severity - удаляем все runs с алертами
                if alerts:
                    runs_to_delete.append(run.id)

        # Удаляем
        if runs_to_delete:
            deleted_count = db.query(ModuleRun).filter(
                ModuleRun.id.in_(runs_to_delete)
            ).delete(synchronize_session=False)

            db.commit()
            logger.info(f"Bulk deleted {deleted_count} module runs with alerts")

            return {
                "status": "ok",
                "message": f"Deleted {deleted_count} alerts",
                "deleted_count": deleted_count
            }
        else:
            return {
                "status": "ok",
                "message": "No alerts to delete",
                "deleted_count": 0
            }

    except Exception as e:
        logger.error(f"Error bulk deleting alerts: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
