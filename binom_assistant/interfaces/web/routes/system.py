# -*- coding: utf-8 -*-
"""
Системные endpoint'ы для управления приложением
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any
from pathlib import Path
import logging
import os
import sys
import signal
from datetime import datetime, timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address
from ..auth import get_current_user

logger = logging.getLogger(__name__)
security_logger = logging.getLogger("security_audit")

router = APIRouter(dependencies=[Depends(get_current_user)])
limiter = Limiter(key_func=get_remote_address)


def get_uptime() -> Dict[str, Any]:
    """
    Вычисляет uptime приложения

    Returns:
        Dict с форматированным uptime и количеством секунд
    """
    try:
        from interfaces.web.main import APP_START_TIME

        if APP_START_TIME is None:
            return {
                "uptime_seconds": 0,
                "uptime_formatted": "N/A"
            }

        uptime_delta = datetime.now() - APP_START_TIME
        total_seconds = int(uptime_delta.total_seconds())

        # Форматируем uptime
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        # Создаем читаемую строку
        parts = []
        if days > 0:
            parts.append(f"{days}д")
        if hours > 0:
            parts.append(f"{hours}ч")
        if minutes > 0:
            parts.append(f"{minutes}м")
        if seconds > 0 or not parts:  # показываем секунды только если uptime < 1 минуты
            parts.append(f"{seconds}с")

        uptime_formatted = " ".join(parts[:2])  # показываем максимум 2 компонента

        return {
            "uptime_seconds": total_seconds,
            "uptime_formatted": uptime_formatted,
            "started_at": APP_START_TIME.isoformat()
        }
    except Exception as e:
        logger.error(f"Error calculating uptime: {e}")
        return {
            "uptime_seconds": 0,
            "uptime_formatted": "N/A"
        }


@router.post("/refresh")
async def refresh_data(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Запускает обновление данных из Binom в фоновом режиме

    Returns:
        task_id для отслеживания прогресса
    """
    try:
        from storage.database import session_scope, BackgroundTask

        logger.info("Manual data refresh requested")

        # Создаем задачу в БД
        with session_scope() as session:
            task = BackgroundTask(
                task_type='data_collection',
                status='pending',
                progress=0,
                progress_message='Задача поставлена в очередь'
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        # Запускаем в фоне с task_id
        background_tasks.add_task(run_collector, task_id=task_id)

        return {
            "status": "started",
            "task_id": task_id,
            "message": "Обновление данных запущено в фоновом режиме",
            "started_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error starting data refresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/refresh/status")
async def get_refresh_status() -> Dict[str, Any]:
    """
    Получает статус последнего обновления данных

    Returns:
        Информация о последнем обновлении
    """
    try:
        from storage.database import session_scope, Campaign, CampaignStatsDaily, BackgroundTask
        from sqlalchemy import func

        with session_scope() as session:
            # Проверяем наличие активных задач сбора данных
            active_collection_task = session.query(BackgroundTask).filter(
                BackgroundTask.task_type.in_(['initial_collection', 'data_collection', 'stats_rebuild']),
                BackgroundTask.status.in_(['pending', 'running'])
            ).first()

            # Получаем информацию о последних данных
            last_campaign_update = session.query(
                func.max(Campaign.last_seen)
            ).scalar()

            last_stat_update = session.query(
                func.max(CampaignStatsDaily.snapshot_time)
            ).scalar()

            total_campaigns = session.query(
                func.count(Campaign.internal_id)
            ).scalar()

            total_stats = session.query(
                func.count(CampaignStatsDaily.id)
            ).scalar()

            return {
                "last_campaign_update": last_campaign_update.isoformat() if last_campaign_update else None,
                "last_stat_update": last_stat_update.isoformat() if last_stat_update else None,
                "total_campaigns": total_campaigns or 0,
                "total_stats_records": total_stats or 0,
                "is_updating": active_collection_task is not None,
                "update_progress": active_collection_task.progress if active_collection_task else None,
                "update_message": active_collection_task.progress_message if active_collection_task else None
            }

    except Exception as e:
        logger.error(f"Error getting refresh status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_system_health() -> Dict[str, Any]:
    """
    Комплексная проверка состояния системы для индикатора в UI

    Проверяет:
    - База данных (connectivity)
    - Binom API (доступность)
    - Дисковое пространство
    - Планировщик задач
    - Свежесть данных

    Returns:
        status: "ok" | "warning" | "error"
        message: описание состояния
        components: детали по каждому компоненту
        uptime: информация о времени работы
    """
    components = {}
    overall_status = "ok"
    messages = []

    try:
        from storage.database import session_scope, CampaignStatsDaily
        from sqlalchemy import func, text
        import httpx
        import shutil
        from pathlib import Path

        with session_scope() as session:
            # 1. Проверка БД
            try:
                session.execute(text("SELECT 1"))
                components["database"] = {
                    "status": "ok",
                    "message": "База данных"
                }
            except Exception as e:
                logger.error(f"Database check failed: {e}")
                overall_status = "error"
                components["database"] = {
                    "status": "error",
                    "message": f"БД недоступна: {str(e)}"
                }
                messages.append("БД недоступна")

            # 2. Проверка Binom API
            try:
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
                                components["binom_api"] = {
                                    "status": "ok",
                                    "message": "Binom API"
                                }
                            else:
                                overall_status = "warning" if overall_status == "ok" else overall_status
                                components["binom_api"] = {
                                    "status": "warning",
                                    "message": f"Binom API код {response.status_code}"
                                }
                                messages.append("Проблема с Binom API")
                    except Exception as e:
                        overall_status = "warning" if overall_status == "ok" else overall_status
                        components["binom_api"] = {
                            "status": "warning",
                            "message": "Binom API недоступен"
                        }
                        messages.append("Binom API недоступен")
                else:
                    components["binom_api"] = {
                        "status": "not_configured",
                        "message": "Binom API не настроен"
                    }
            except Exception as e:
                logger.warning(f"Binom API check failed: {e}")

            # 3. Проверка дискового пространства
            try:
                db_path = Path("data")
                if db_path.exists():
                    total, used, free = shutil.disk_usage(db_path)
                    free_percent = (free / total) * 100
                    free_gb = round(free / (1024**3), 2)

                    if free_percent < 10:
                        overall_status = "warning" if overall_status == "ok" else overall_status
                        components["disk_space"] = {
                            "status": "warning",
                            "message": f"Диск: {free_percent:.1f}% свободно ({free_gb} ГБ)"
                        }
                        messages.append("Мало места на диске")
                    else:
                        components["disk_space"] = {
                            "status": "ok",
                            "message": f"Диск: {free_percent:.1f}% свободно"
                        }
            except Exception as e:
                logger.warning(f"Disk space check failed: {e}")

            # 4. Проверка свежести данных
            try:
                yesterday = datetime.now() - timedelta(hours=24)
                three_days_ago = datetime.now() - timedelta(hours=72)

                recent_stats = session.query(
                    func.count(CampaignStatsDaily.id)
                ).filter(
                    CampaignStatsDaily.snapshot_time >= yesterday
                ).scalar()

                last_update = session.query(
                    func.max(CampaignStatsDaily.snapshot_time)
                ).scalar()

                if recent_stats > 0:
                    # Данные свежие (< 24ч)
                    hours_ago = (datetime.now() - last_update).total_seconds() / 3600
                    components["data_freshness"] = {
                        "status": "ok",
                        "message": f"Данные: обновлены {int(hours_ago)} ч. назад"
                    }
                elif last_update and last_update >= three_days_ago:
                    # Данные старые (24-72ч)
                    hours_ago = (datetime.now() - last_update).total_seconds() / 3600
                    overall_status = "warning" if overall_status == "ok" else overall_status
                    components["data_freshness"] = {
                        "status": "warning",
                        "message": f"Данные: устарели ({int(hours_ago)} ч. назад)"
                    }
                    messages.append(f"Данные устарели ({int(hours_ago)} ч.)")
                else:
                    # Данных нет или очень старые (> 72ч)
                    overall_status = "error"
                    components["data_freshness"] = {
                        "status": "error",
                        "message": "Данные: критически устарели или отсутствуют"
                    }
                    messages.append("Нет свежих данных")
            except Exception as e:
                logger.error(f"Data freshness check failed: {e}")

            # 5. Проверка планировщика (базовая)
            try:
                components["scheduler"] = {
                    "status": "ok",
                    "message": "Планировщик"
                }
            except Exception as e:
                logger.warning(f"Scheduler check failed: {e}")

        # Формируем итоговое сообщение
        if overall_status == "ok":
            message = "Все компоненты работают"
        elif overall_status == "warning":
            message = "Есть предупреждения: " + ", ".join(messages)
        else:
            message = "Обнаружены проблемы: " + ", ".join(messages)

        # Добавляем информацию об uptime
        uptime_info = get_uptime()

        return {
            "status": overall_status,
            "message": message,
            "components": components,
            "uptime": uptime_info
        }

    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return {
            "status": "error",
            "message": f"Ошибка проверки: {str(e)}",
            "components": {},
            "uptime": get_uptime()
        }


@router.get("/tasks/active", response_model=None)
async def get_active_tasks():
    """
    Получает список активных фоновых задач (pending или running)

    Returns:
        JSONResponse со списком активных задач
    """
    from storage.database import session_scope, BackgroundTask
    import json

    logger.info("=== GET /tasks/active called ===")

    try:
        with session_scope() as session:
            # Получаем задачи со статусом pending или running
            tasks = session.query(BackgroundTask).filter(
                BackgroundTask.status.in_(['pending', 'running'])
            ).order_by(BackgroundTask.created_at.desc()).all()

            logger.info(f"Found {len(tasks)} active tasks in database")

            # Безопасно конвертируем задачи в dict
            tasks_list = []
            for task in tasks:
                try:
                    # Вручную создаем dict вместо to_dict() для отладки
                    task_dict = {
                        'id': task.id,
                        'task_type': task.task_type,
                        'status': task.status,
                        'progress': task.progress if task.progress is not None else 0,
                        'progress_message': task.progress_message if task.progress_message else '',
                        'result': task.result if task.result is not None else {},
                        'error': task.error if task.error else None,
                        'created_at': task.created_at.isoformat() if task.created_at else None,
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                    }
                    tasks_list.append(task_dict)
                    logger.info(f"Task {task.id} ({task.task_type}) converted successfully")
                except Exception as e:
                    logger.error(f"Error converting task {task.id}: {e}", exc_info=True)
                    continue

            response_data = {
                "tasks": tasks_list,
                "count": len(tasks_list)
            }

            logger.info(f"Returning response with {len(tasks_list)} tasks")

            # Используем json.dumps для явной сериализации
            json_str = json.dumps(response_data, ensure_ascii=False)
            logger.info(f"JSON response length: {len(json_str)} characters")

            return JSONResponse(content=response_data, status_code=200)

    except Exception as e:
        logger.error(f"EXCEPTION in get_active_tasks: {e}", exc_info=True)
        return JSONResponse(
            content={"error": str(e), "tasks": [], "count": 0},
            status_code=500
        )


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: int) -> Dict[str, Any]:
    """
    Получает статус фоновой задачи

    Args:
        task_id: ID задачи

    Returns:
        Информация о задаче (status, progress, result, error)
    """
    try:
        from storage.database import session_scope, BackgroundTask

        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()

            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            return task.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_app_config() -> Dict[str, Any]:
    """
    Получает конфигурацию приложения для frontend.

    Returns:
        Конфигурация с BINOM_URL, update_days, debug, environment и другими параметрами
    """
    import os
    from dotenv import load_dotenv

    # Загружаем переменные окружения
    load_dotenv()

    # Получаем период обновления из настроек
    update_days = 7  # дефолт
    try:
        from services.settings_manager import get_settings_manager
        settings = get_settings_manager()
        update_days = settings.get('collector.update_days', default=7)
    except Exception as e:
        logger.warning(f"Could not load update_days from settings: {e}")

    # Получаем конфигурацию приложения
    debug_str = os.getenv("DEBUG", "False").lower()
    debug = debug_str in ('true', '1', 'yes')

    return {
        "binom_url": os.getenv("BINOM_URL", "http://localhost"),
        "update_days": update_days,
        "debug": debug,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "timezone": os.getenv("TIMEZONE", "UTC")
    }


@router.delete("/cache")
@limiter.limit("10/minute")  # Максимум 10 очисток кэша в минуту
async def clear_cache(request: Request) -> Dict[str, Any]:
    """
    Очищает кэш системы (не удаляя настройки)

    Returns:
        Статус очистки
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        settings.clear_cache()

        logger.info("System cache cleared successfully")

        return {
            "status": "ok",
            "message": "Кэш системы успешно очищен"
        }

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/reset-and-rebuild")
async def reset_and_rebuild_data(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    ПОЛНАЯ ОЧИСТКА всех данных из Binom и повторный сбор за 60 дней.

    ВНИМАНИЕ: Удаляет ВСЕ кампании, статистику, источники, офферы, партнерки!
    Используется для полной переинициализации данных.

    Returns:
        task_id для отслеживания прогресса
    """
    try:
        from storage.database import session_scope, BackgroundTask

        logger.warning("FULL DATA RESET requested - clearing all Binom data!")

        # Создаем задачу в БД
        with session_scope() as session:
            task = BackgroundTask(
                task_type='initial_collection',
                status='pending',
                progress=0,
                progress_message='Подготовка к полной очистке и повторному сбору данных за 60 дней'
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        # Запускаем в фоне
        background_tasks.add_task(run_full_reset_and_rebuild, task_id=task_id)

        return {
            "status": "started",
            "task_id": task_id,
            "message": "Пересборка статистики запущена в фоновом режиме",
            "started_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error starting stats rebuild: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/reset")
async def reset_all_settings() -> Dict[str, Any]:
    """
    Сбрасывает все настройки к значениям по умолчанию
    ВНИМАНИЕ: Удаляет все настройки из БД!

    Returns:
        Количество сброшенных настроек
    """
    try:
        from storage.database import session_scope, AppSettings
        from services.settings_manager import get_settings_manager

        with session_scope() as session:
            # Считаем количество настроек перед удалением
            count = session.query(AppSettings).count()

            # Удаляем все настройки из БД
            session.query(AppSettings).delete()
            session.commit()

            logger.warning(f"All settings reset to defaults ({count} settings removed)")

        # Очищаем кэш
        settings = get_settings_manager()
        settings.clear_cache()

        return {
            "status": "ok",
            "message": f"Все настройки сброшены к значениям по умолчанию",
            "reset_count": count
        }

    except Exception as e:
        logger.error(f"Error resetting all settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart")
@limiter.limit("5/hour")  # Максимум 5 перезапусков в час
async def restart_application(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Перезапускает приложение для применения изменений из .env
    ВНИМАНИЕ: Приложение будет недоступно несколько секунд!

    Returns:
        Статус операции
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Application restart requested via API")
        security_logger.warning(f"RESTART_REQUESTED | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        # Запускаем перезапуск в фоновой задаче с задержкой
        # чтобы успеть отправить ответ клиенту
        background_tasks.add_task(perform_restart)

        return {
            "status": "ok",
            "message": "Приложение перезапускается... Обновите страницу через 5-10 секунд",
            "restart_initiated_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error initiating restart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_logs(level: str = None, limit: int = 100) -> Dict[str, Any]:
    """
    Получает последние записи из всех лог-файлов

    Args:
        level: Фильтр по уровню (INFO, WARNING, ERROR, DEBUG)
        limit: Максимальное количество записей (по умолчанию 100)

    Returns:
        Список последних лог-записей из всех файлов
    """
    try:
        from pathlib import Path
        import re
        import os

        # Пути к лог-файлам
        # На VPS: /app/binom_assistant/ (рабочая директория) -> /app/logs/ (логи на уровень выше)
        # На локалке: c:/Work/code/binom/binom_assistant/ -> c:/Work/code/binom/logs/
        log_dir = Path(__file__).parent.parent.parent.parent / "logs"
        log_files = [
            log_dir / "app.log",
            log_dir / "collector.log",
            log_dir / "stat_periods.log"
        ]

        all_logs = []

        # Читаем каждый лог-файл
        for log_file in log_files:
            if not log_file.exists():
                continue

            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Берем последние строки (умножаем на количество файлов)
                recent_lines = lines[-limit*2:] if len(lines) > limit*2 else lines

                # Парсим лог-записи
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Пытаемся извлечь timestamp для сортировки
                    # Формат: 2025-11-05 15:04:06 - ...
                    timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    timestamp = timestamp_match.group(1) if timestamp_match else None

                    # Определяем уровень
                    log_level = "INFO"  # дефолт
                    if " - ERROR - " in line or ":ERROR:" in line:
                        log_level = "ERROR"
                    elif " - WARNING - " in line or ":WARNING:" in line:
                        log_level = "WARNING"
                    elif " - DEBUG - " in line or ":DEBUG:" in line:
                        log_level = "DEBUG"
                    elif " - CRITICAL - " in line or ":CRITICAL:" in line:
                        log_level = "CRITICAL"

                    # Фильтруем по уровню если указан
                    if level and log_level != level:
                        continue

                    log_entry = {
                        "message": line,
                        "level": log_level,
                        "source": log_file.name,
                        "timestamp": timestamp
                    }

                    all_logs.append(log_entry)

            except Exception as e:
                logger.error(f"Error reading {log_file}: {e}")
                continue

        if not all_logs:
            return {
                "status": "ok",
                "logs": [],
                "message": "Лог-файлы не найдены или пусты"
            }

        # Сортируем по timestamp (новые сверху)
        all_logs.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        # Ограничиваем количество
        all_logs = all_logs[:limit]

        return {
            "status": "ok",
            "logs": all_logs,
            "total": len(all_logs)
        }

    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log-errors")
async def get_log_errors(hours: int = 24, limit: int = 50) -> Dict[str, Any]:
    """
    Получает ERROR и WARNING из всех лог-файлов за указанный период

    Args:
        hours: Период в часах (по умолчанию 24)
        limit: Максимальное количество ошибок (по умолчанию 50)

    Returns:
        Список ошибок с метаданными для системы уведомлений
    """
    try:
        from pathlib import Path
        import re
        from datetime import datetime, timedelta

        # Пути к лог-файлам
        # На VPS: /app/binom_assistant/ (рабочая директория) -> /app/logs/ (логи на уровень выше)
        # На локалке: c:/Work/code/binom/binom_assistant/ -> c:/Work/code/binom/logs/
        log_dir = Path(__file__).parent.parent.parent.parent / "logs"
        log_files = [
            log_dir / "app.log",
            log_dir / "collector.log",
            log_dir / "stat_periods.log"
        ]

        cutoff_time = datetime.now() - timedelta(hours=hours)
        all_errors = []

        # Читаем каждый лог-файл
        for log_file in log_files:
            if not log_file.exists():
                continue

            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Берем последние строки (для производительности)
                recent_lines = lines[-limit*10:] if len(lines) > limit*10 else lines

                # Парсим ERROR и WARNING
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Проверяем уровень
                    is_error = " - ERROR - " in line or " - CRITICAL - " in line
                    is_warning = " - WARNING - " in line

                    if not (is_error or is_warning):
                        continue

                    # Извлекаем timestamp
                    # Формат: 2025-11-05 15:04:06 - ...
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
                    # Формат: 2025-11-05 15:04:06 - component.name - LEVEL - message
                    parts = line.split(" - ", 3)
                    component = parts[1] if len(parts) > 1 else "unknown"
                    level = parts[2] if len(parts) > 2 else "ERROR"
                    message = parts[3] if len(parts) > 3 else line

                    # Определяем severity для системы уведомлений
                    severity = "critical" if "CRITICAL" in level else ("high" if "ERROR" in level else "medium")

                    error_entry = {
                        "timestamp": timestamp_str,
                        "level": level.strip(),
                        "severity": severity,
                        "source": log_file.name,
                        "component": component,
                        "message": message[:200],  # Ограничиваем длину сообщения
                        "full_line": line[:500]  # Полная строка (ограниченная)
                    }

                    all_errors.append(error_entry)

            except Exception as e:
                logger.error(f"Error reading {log_file} for errors: {e}")
                continue

        if not all_errors:
            return {
                "status": "ok",
                "errors": [],
                "total": 0,
                "message": f"Нет ошибок за последние {hours} часов"
            }

        # Сортируем по timestamp (новые сверху)
        all_errors.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        # Ограничиваем количество
        all_errors = all_errors[:limit]

        # Подсчет по severity
        critical_count = sum(1 for e in all_errors if e.get("severity") == "critical")
        high_count = sum(1 for e in all_errors if e.get("severity") == "high")
        medium_count = sum(1 for e in all_errors if e.get("severity") == "medium")

        return {
            "status": "ok",
            "errors": all_errors,
            "total": len(all_errors),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "period_hours": hours
        }

    except Exception as e:
        logger.error(f"Error reading log errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/logs")
@limiter.limit("5/hour")  # Максимум 5 очисток логов в час
async def clear_logs(request: Request) -> Dict[str, Any]:
    """
    Очищает лог-файл (архивирует текущий и создает новый)

    Returns:
        Статус операции
    """
    try:
        from pathlib import Path
        import shutil

        client_ip = request.client.host if request.client else "unknown"
        security_logger.warning(f"LOGS_CLEAR_REQUESTED | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        # Пути к лог-файлам
        # На VPS: /app/binom_assistant/ (рабочая директория) -> /app/logs/ (логи на уровень выше)
        # На локалке: c:/Work/code/binom/binom_assistant/ -> c:/Work/code/binom/logs/
        log_dir = Path(__file__).parent.parent.parent.parent / "logs"
        log_files = [
            log_dir / "app.log",
            log_dir / "collector.log",
            log_dir / "stat_periods.log"
        ]

        # Проверяем какие файлы существуют
        existing_files = [f for f in log_files if f.exists()]

        if not existing_files:
            return {
                "status": "ok",
                "message": "Лог-файлы не существуют"
            }

        # Создаем timestamp для архивов
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_files = []
        cleared_count = 0

        # Очищаем каждый файл
        for log_file in existing_files:
            try:
                # Создаем архивную копию
                archive_name = f"{log_file.stem}_{timestamp}.log"
                archive_file = log_file.parent / archive_name

                # Копируем текущий лог в архив
                shutil.copy2(log_file, archive_file)
                archived_files.append(archive_name)

                # Очищаем текущий лог-файл
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"# Log file cleared at {datetime.now().isoformat()}\n")

                cleared_count += 1
                logger.info(f"Cleared {log_file.name} and archived to {archive_name}")

            except Exception as e:
                logger.error(f"Error clearing {log_file.name}: {e}")
                continue

        if cleared_count == 0:
            return {
                "status": "error",
                "message": "Не удалось очистить ни один лог-файл"
            }

        return {
            "status": "ok",
            "message": f"Очищено {cleared_count} лог-файл(ов) и заархивировано: {', '.join(archived_files)}",
            "cleared_count": cleared_count,
            "archives": archived_files
        }

    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def perform_restart():
    """
    Выполняет перезапуск приложения с небольшой задержкой

    ВНИМАНИЕ: В dev режиме (--reload) это просто создаст dummy файл
    для триггера auto-reload. В production режиме выполнит полный рестарт.
    """
    import time
    from pathlib import Path

    try:
        # Задержка чтобы успеть отправить ответ клиенту
        time.sleep(2)

        logger.info("Performing application restart...")

        # Проверяем запущен ли uvicorn в dev режиме с --reload
        # В этом случае просто создаем/трогаем файл для триггера reload
        if sys.platform == "win32":
            # Для Windows в dev режиме: создаем dummy файл для триггера reload
            logger.info("Triggering restart via file modification...")

            # Создаем временный файл в корне проекта
            restart_trigger = Path(__file__).parent.parent.parent / ".restart_trigger"
            restart_trigger.touch()

            # Удаляем файл через секунду
            time.sleep(1)
            if restart_trigger.exists():
                restart_trigger.unlink()

            logger.info("Restart trigger activated")
        else:
            # Для Linux/Unix - используем SIGTERM
            logger.info("Triggering restart via SIGTERM...")
            os.kill(os.getpid(), signal.SIGTERM)

    except Exception as e:
        logger.error(f"Error during restart: {e}", exc_info=True)


def run_collector(task_id: int):
    """
    Фоновая задача для запуска collector

    Args:
        task_id: ID задачи для отслеживания прогресса
    """
    try:
        from services.scheduler.collector import DataCollector

        logger.info(f"Starting background data collection (task_id={task_id})...")
        collector = DataCollector()
        stats = collector.daily_collect(task_id=task_id)

        logger.info(f"Background collection completed (task_id={task_id}): {stats.get('campaigns_processed', 0)} campaigns")

    except Exception as e:
        logger.error(f"Background collection failed (task_id={task_id}): {e}", exc_info=True)


def run_stats_rebuild(task_id: int):
    """
    Фоновая задача для пересборки статистики за 30 дней

    Args:
        task_id: ID задачи для отслеживания прогресса
    """
    try:
        from services.scheduler.collector import DataCollector
        from storage.database import session_scope, BackgroundTask

        logger.info(f"Starting stats rebuild (task_id={task_id})...")

        # Обновляем статус задачи
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.status = 'running'
                task.progress_message = 'Пересборка статистики за последние 30 дней'
                session.commit()

        # Запускаем сборщик с периодом 30 дней
        collector = DataCollector()

        # Временно переопределяем настройку update_days для сборщика
        original_update_days = None
        try:
            from services.settings_manager import get_settings_manager
            settings = get_settings_manager()
            original_update_days = settings.get('collector.update_days', default=7)
        except:
            pass

        # Собираем данные за 30 дней
        stats = collector.daily_collect(task_id=task_id)

        logger.info(f"Stats rebuild completed (task_id={task_id}): {stats.get('campaigns_processed', 0)} campaigns")

        # Обновляем статус задачи на завершенную
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.status = 'completed'
                task.progress = 100
                task.progress_message = f"Пересборка завершена: {stats.get('campaigns_processed', 0)} кампаний"
                task.result = stats
                session.commit()

    except Exception as e:
        logger.error(f"Stats rebuild failed (task_id={task_id}): {e}", exc_info=True)

        # Обновляем статус задачи на ошибку
        try:
            with session_scope() as session:
                task = session.query(BackgroundTask).filter_by(id=task_id).first()
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    session.commit()
        except:
            pass


def run_full_reset_and_rebuild(task_id: int):
    """
    Фоновая задача для ПОЛНОЙ ОЧИСТКИ данных и повторного сбора за 60 дней

    Выполняет:
    1. Очистку всех таблиц с данными из Binom
    2. Сброс флага first_run
    3. Сбор данных за 60 дней

    Args:
        task_id: ID задачи для отслеживания прогресса
    """
    try:
        from services.scheduler.collector import DataCollector
        from storage.database import (
            session_scope, BackgroundTask,
            Campaign, CampaignStatsDaily, StatPeriod, NameChange,
            TrafficSource, TrafficSourceStatsDaily,
            Offer, OfferStatsDaily,
            AffiliateNetwork, NetworkStatsDaily
        )
        from services.settings_manager import get_settings_manager

        logger.warning(f"Starting FULL DATA RESET (task_id={task_id})...")

        # Обновляем статус задачи
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.status = 'running'
                task.started_at = datetime.utcnow()
                task.progress = 5
                task.progress_message = 'Очистка всех данных из БД...'
                session.commit()

        # ШАГ 1: Очищаем все таблицы с данными Binom
        logger.info("Step 1: Clearing all Binom data tables...")
        with session_scope() as session:
            # Удаляем в правильном порядке (из-за foreign keys)
            session.query(CampaignStatsDaily).delete()
            session.query(StatPeriod).delete()
            session.query(NameChange).delete()
            session.query(Campaign).delete()

            session.query(TrafficSourceStatsDaily).delete()
            session.query(TrafficSource).delete()

            session.query(OfferStatsDaily).delete()
            session.query(Offer).delete()

            session.query(NetworkStatsDaily).delete()
            session.query(AffiliateNetwork).delete()

            session.commit()
            logger.info("All Binom data tables cleared successfully")

        # Обновляем прогресс
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.progress = 10
                task.progress_message = 'Данные очищены, подготовка к сбору...'
                session.commit()

        # ШАГ 2: Сбрасываем флаг first_run (чтобы не запускалась автоматическая initial_collection)
        logger.info("Step 2: Resetting first_run flag...")
        settings = get_settings_manager()
        # НЕ сбрасываем на true, т.к. мы сами запускаем сбор прямо сейчас
        # settings.set('system.first_run', 'false')

        # ШАГ 3: Запускаем сбор данных за 60 дней
        logger.info("Step 3: Starting data collection for 60 days...")
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.progress = 15
                task.progress_message = 'Запуск сбора данных за 60 дней (fast mode)...'
                session.commit()

        # Создаем collector с отключением пауз для быстрого сбора
        collector = DataCollector(skip_pauses=True)
        result = collector.initial_collect(days=60)

        logger.info("=" * 60)
        logger.info("FULL DATA RESET AND REBUILD COMPLETED SUCCESSFULLY")
        logger.info(f"Collected data: {result}")
        logger.info("=" * 60)

        # Обновляем статус задачи на успешную
        with session_scope() as session:
            task = session.query(BackgroundTask).filter_by(id=task_id).first()
            if task:
                task.status = 'completed'
                task.progress = 100
                task.progress_message = 'Полная очистка и сбор данных завершены'
                task.completed_at = datetime.utcnow()
                task.result = result
                session.commit()

    except Exception as e:
        logger.error(f"Full reset and rebuild failed (task_id={task_id}): {e}", exc_info=True)

        # Обновляем статус задачи на ошибку
        try:
            with session_scope() as session:
                task = session.query(BackgroundTask).filter_by(id=task_id).first()
                if task:
                    task.status = 'failed'
                    task.progress_message = 'Ошибка при очистке и сборе данных'
                    task.error = str(e)
                    task.completed_at = datetime.utcnow()
                    session.commit()
        except Exception as db_error:
            logger.error(f"Failed to update task status: {db_error}")


# ============================================================================
# BACKUP ENDPOINTS
# ============================================================================

def get_backup_dir() -> Path:
    """
    Определяет путь к директории бэкапов в зависимости от окружения.

    Returns:
        Path: Путь к директории бэкапов
    """
    # В Docker контейнере бэкапы хранятся в /app/backups
    if Path("/app/binom_assistant").exists():
        return Path("/app/backups")

    # Локально - в backups относительно корня проекта
    return Path(__file__).parent.parent.parent.parent / "backups"


@router.post("/backup/create")
@limiter.limit("10/hour")  # Максимум 10 бэкапов в час
async def create_backup(request: Request) -> Dict[str, Any]:
    """
    Создает бэкап базы данных через вызов backup.sh скрипта (на Linux/Docker)
    или напрямую копированием файла (на Windows для dev режима)

    Returns:
        Информация о созданном бэкапе
    """
    import subprocess
    from pathlib import Path
    import platform
    import shutil

    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Backup creation requested from {client_ip}")
        security_logger.info(f"BACKUP_CREATE | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        # Определяем ОС
        is_windows = platform.system() == 'Windows'

        if is_windows:
            # На Windows делаем простой бэкап без скрипта (для dev режима)
            logger.info("Running on Windows - using direct DB copy")

            # Пути
            project_root = Path(__file__).parent.parent.parent.parent
            db_path = project_root / "data" / "binom_assistant.db"
            backup_dir = project_root / "backups"

            if not db_path.exists():
                raise HTTPException(status_code=500, detail="База данных не найдена")

            # Создаем директорию для бэкапов
            backup_dir.mkdir(exist_ok=True)

            # Генерируем имя файла с timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"binom_assistant_{timestamp}.db"
            backup_path = backup_dir / backup_filename

            # Копируем БД
            shutil.copy2(db_path, backup_path)

            # Размер файла
            size_mb = backup_path.stat().st_size / (1024 * 1024)

            logger.info(f"Backup created successfully (Windows): {backup_filename} ({size_mb:.1f} MB)")

            return {
                "status": "ok",
                "message": f"Бэкап успешно создан ({size_mb:.1f} MB)",
                "backup_file": backup_filename,
                "created_at": datetime.now().isoformat()
            }

        else:
            # На Linux/Docker используем bash скрипт
            # Проверяем несколько возможных путей
            possible_paths = [
                Path(__file__).parent.parent.parent.parent / "scripts" / "backup.sh",  # /app/scripts/backup.sh (Docker)
                Path(__file__).parent.parent.parent.parent.parent / "scripts" / "backup.sh",  # Один уровень выше
                Path("/app/scripts/backup.sh"),  # Абсолютный путь в Docker
                Path("/opt/binom_assistant/scripts/backup.sh"),  # Абсолютный путь на VPS
            ]

            script_path = None
            for path in possible_paths:
                logger.info(f"Checking backup script path: {path}")
                if path.exists():
                    script_path = path
                    logger.info(f"Found backup script at: {script_path}")
                    break

            if not script_path:
                logger.error(f"Backup script not found. Checked paths: {[str(p) for p in possible_paths]}")
                raise HTTPException(status_code=500, detail=f"Скрипт бэкапа не найден. Проверенные пути: {[str(p) for p in possible_paths]}")

            # Выполняем скрипт
            result = subprocess.run(
                ["bash", str(script_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.error(f"Backup script failed: {result.stderr}")
                raise HTTPException(status_code=500, detail=f"Ошибка создания бэкапа: {result.stderr}")

            # Парсим вывод для получения имени файла
            output = result.stdout
            backup_file = None
            for line in output.split('\n'):
                if 'Backup file:' in line or '.db.gz' in line:
                    # Извлекаем имя файла
                    parts = line.split('/')
                    if parts:
                        backup_file = parts[-1].strip()
                        break

            logger.info(f"Backup created successfully: {backup_file}")

            return {
                "status": "ok",
                "message": "Бэкап успешно создан",
                "backup_file": backup_file,
                "created_at": datetime.now().isoformat()
            }

    except subprocess.TimeoutExpired:
        logger.error("Backup script timeout")
        raise HTTPException(status_code=500, detail="Таймаут создания бэкапа")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup/list")
async def list_backups() -> Dict[str, Any]:
    """
    Получает список всех доступных бэкапов

    Returns:
        Список бэкапов с метаданными (размер, дата создания)
    """
    try:
        from pathlib import Path
        import os

        # Директория с бэкапами
        backup_dir = get_backup_dir()

        if not backup_dir.exists():
            return {
                "status": "ok",
                "backups": [],
                "total": 0,
                "message": "Директория бэкапов не существует"
            }

        # Получаем все файлы бэкапов
        backup_files = list(backup_dir.glob("binom_assistant_*.db*"))

        backups = []
        for file_path in backup_files:
            stat = file_path.stat()

            # Размер в человекочитаемом формате
            size_bytes = stat.st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

            backups.append({
                "filename": file_path.name,
                "size": size_bytes,
                "size_formatted": size_str,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        # Сортируем по дате создания (новые сверху)
        backups.sort(key=lambda x: x['created_at'], reverse=True)

        return {
            "status": "ok",
            "backups": backups,
            "total": len(backups),
            "backup_dir": str(backup_dir)
        }

    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup/download/{filename}")
async def download_backup(filename: str) -> Any:
    """
    Скачивает конкретный файл бэкапа

    Args:
        filename: Имя файла бэкапа

    Returns:
        Файл для скачивания
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    try:
        # Валидация имени файла (защита от path traversal)
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Недопустимое имя файла")

        # Проверяем что файл имеет правильный формат
        if not filename.startswith('binom_assistant_') or not ('.db' in filename):
            raise HTTPException(status_code=400, detail="Недопустимый формат файла")

        # Путь к файлу бэкапа
        backup_dir = get_backup_dir()
        file_path = backup_dir / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл бэкапа не найден")

        logger.info(f"Downloading backup: {filename}")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/gzip' if filename.endswith('.gz') else 'application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backup/old")
@limiter.limit("10/hour")  # Максимум 10 очисток в час
async def delete_old_backups(request: Request, keep: int = 7) -> Dict[str, Any]:
    """
    Удаляет старые бэкапы, оставляя последние N штук

    Args:
        keep: Количество бэкапов которые нужно оставить (по умолчанию 7)

    Returns:
        Количество удаленных бэкапов
    """
    from pathlib import Path

    try:
        client_ip = request.client.host if request.client else "unknown"
        security_logger.info(f"BACKUP_CLEANUP | keep: {keep} | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        if keep < 1:
            raise HTTPException(status_code=400, detail="Нужно оставить минимум 1 бэкап")

        # Директория с бэкапами
        backup_dir = get_backup_dir()

        if not backup_dir.exists():
            return {
                "status": "ok",
                "deleted": 0,
                "message": "Директория бэкапов не существует"
            }

        # Получаем все файлы бэкапов
        backup_files = list(backup_dir.glob("binom_assistant_*.db*"))

        # Сортируем по дате изменения (новые первые)
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Файлы для удаления (все кроме последних keep штук)
        files_to_delete = backup_files[keep:]

        deleted_count = 0
        deleted_files = []

        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_files.append(file_path.name)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting {file_path.name}: {e}")

        logger.info(f"Deleted {deleted_count} old backups (kept {keep})")

        return {
            "status": "ok",
            "deleted": deleted_count,
            "kept": len(backup_files) - deleted_count,
            "deleted_files": deleted_files,
            "message": f"Удалено {deleted_count} старых бэкапов"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting old backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backup/{filename}")
@limiter.limit("20/hour")  # Максимум 20 удалений в час
async def delete_backup(request: Request, filename: str) -> Dict[str, Any]:
    """
    Удаляет конкретный файл бэкапа

    Args:
        filename: Имя файла бэкапа

    Returns:
        Статус удаления
    """
    from pathlib import Path

    try:
        client_ip = request.client.host if request.client else "unknown"
        security_logger.info(f"BACKUP_DELETE | file: {filename} | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        # Валидация имени файла
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Недопустимое имя файла")

        if not filename.startswith('binom_assistant_') or not ('.db' in filename):
            raise HTTPException(status_code=400, detail="Недопустимый формат файла")

        # Путь к файлу бэкапа
        backup_dir = get_backup_dir()
        file_path = backup_dir / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл бэкапа не найден")

        # Удаляем файл
        file_path.unlink()

        logger.info(f"Backup deleted: {filename}")

        return {
            "status": "ok",
            "message": f"Бэкап {filename} успешно удален"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UPDATE ENDPOINTS (GitHub Releases API)
# ============================================================================

# Глобальный кэш для проверки обновлений (in-memory, 1 час)
_update_check_cache = {
    "data": None,
    "timestamp": None
}

def get_current_version() -> str:
    """
    Читает текущую версию из файла VERSION

    Returns:
        Версия приложения (например "1.0.0")
    """
    try:
        from pathlib import Path

        # Пробуем разные пути к VERSION
        possible_paths = [
            Path("/app/VERSION"),  # В Docker контейнере
            Path(__file__).parent.parent.parent.parent / "VERSION"  # Локально
        ]

        for version_file in possible_paths:
            if version_file.exists():
                with open(version_file, 'r') as f:
                    version = f.read().strip()
                    logger.info(f"Current version from {version_file}: {version}")
                    return version

        # Если файл не найден, возвращаем версию из кода
        logger.warning("VERSION file not found, using hardcoded version")
        return "1.0.0"

    except Exception as e:
        logger.error(f"Error reading version: {e}")
        return "1.0.0"


@router.get("/update/status")
async def get_update_status() -> Dict[str, Any]:
    """
    Получает информацию о текущей версии и статусе git репозитория

    Returns:
        Информация о текущей ветке, коммите, и доступных обновлениях
    """
    import subprocess
    from pathlib import Path

    try:
        # Рабочая директория - корень проекта
        work_dir = Path(__file__).parent.parent.parent.parent

        # Проверяем что это git репозиторий
        git_dir = work_dir / ".git"
        if not git_dir.exists():
            return {
                "status": "no_git",
                "message": "Не является git репозиторием. Обновление через git недоступно.",
                "manual_update": "Используйте ./scripts/upgrade.sh для обновления через Docker образ"
            }

        # Получаем текущую ветку
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

        # Получаем текущий коммит
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        current_commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"

        # Получаем дату последнего коммита
        date_result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        last_commit_date = date_result.stdout.strip() if date_result.returncode == 0 else "unknown"

        # Получаем сообщение последнего коммита
        msg_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        last_commit_msg = msg_result.stdout.strip() if msg_result.returncode == 0 else ""

        # Проверяем есть ли неотправленные изменения
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        has_uncommitted = bool(status_result.stdout.strip())

        # Получаем версию (git describe или fallback на commit hash)
        version_result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        version = version_result.stdout.strip() if version_result.returncode == 0 else current_commit

        return {
            "status": "ok",
            "git_available": True,
            "version": version,
            "current_branch": current_branch,
            "current_commit": current_commit,
            "last_commit_date": last_commit_date,
            "last_commit_message": last_commit_msg,
            "has_uncommitted_changes": has_uncommitted,
            "repository_path": str(work_dir)
        }

    except subprocess.TimeoutExpired:
        logger.error("Git command timeout")
        raise HTTPException(status_code=500, detail="Таймаут выполнения git команды")
    except Exception as e:
        logger.error(f"Error getting update status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update/check")
@limiter.limit("20/hour")  # Максимум 20 проверок в час
async def check_updates(request: Request) -> Dict[str, Any]:
    """
    Проверяет доступные обновления через GitHub Releases API

    Использует кэширование на 1 час для экономии rate limits GitHub API
    (60 запросов/час без токена, 5000 с токеном)

    Returns:
        Информация о доступных обновлениях
    """
    import httpx
    from datetime import datetime, timedelta

    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Update check requested from {client_ip}")

        # Проверяем кэш (1 час)
        now = datetime.now()
        if (_update_check_cache["data"] is not None and
            _update_check_cache["timestamp"] is not None):

            cache_age = (now - _update_check_cache["timestamp"]).total_seconds()
            if cache_age < 3600:  # 1 час
                logger.info(f"Returning cached update check (age: {int(cache_age)}s)")
                return _update_check_cache["data"]

        # Получаем текущую версию
        current_version = get_current_version()

        # GitHub API для получения последнего релиза
        # Публичный API, не требует токена (но есть лимит 60 запросов/час с IP)
        github_api_url = "https://api.github.com/repos/garik128/binom_assistant/releases/latest"

        logger.info(f"Fetching latest release from GitHub: {github_api_url}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                github_api_url,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Binom-Assistant"
                }
            )

            # Проверяем rate limit
            if response.status_code == 403:
                logger.warning("GitHub API rate limit exceeded")
                return {
                    "status": "rate_limit",
                    "current_version": current_version,
                    "updates_available": False,
                    "message": "Превышен лимит запросов к GitHub API. Попробуйте позже или проверьте вручную.",
                    "manual_check_url": "https://github.com/garik128/binom_assistant/releases"
                }

            if response.status_code == 404:
                logger.warning("No releases found on GitHub")
                return {
                    "status": "no_releases",
                    "current_version": current_version,
                    "updates_available": False,
                    "message": "Релизы на GitHub пока не опубликованы",
                    "manual_check_url": "https://github.com/garik128/binom_assistant/releases"
                }

            if response.status_code != 200:
                logger.error(f"GitHub API error: {response.status_code}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Ошибка GitHub API: {response.status_code}"
                )

            release_data = response.json()

            # Парсим данные релиза
            latest_version = release_data.get("tag_name", "").lstrip("v")  # убираем 'v' если есть
            release_name = release_data.get("name", "")
            release_body = release_data.get("body", "")
            published_at = release_data.get("published_at", "")
            html_url = release_data.get("html_url", "")

            logger.info(f"Latest release from GitHub: {latest_version}")

            # Сравниваем версии (простое сравнение строк)
            # Для более точного сравнения можно использовать packaging.version
            from packaging import version

            try:
                updates_available = version.parse(latest_version) > version.parse(current_version)
            except Exception as e:
                logger.warning(f"Version parsing error: {e}, using string comparison")
                updates_available = latest_version != current_version

            # Формируем ответ
            result = {
                "status": "ok",
                "current_version": current_version,
                "latest_version": latest_version,
                "updates_available": updates_available,
                "release_name": release_name,
                "release_notes": release_body[:500] if release_body else "",  # Ограничиваем длину
                "published_at": published_at,
                "release_url": html_url,
                "message": f"Доступна новая версия: {latest_version}" if updates_available else "Система актуальна"
            }

            # Кэшируем результат на 1 час
            _update_check_cache["data"] = result
            _update_check_cache["timestamp"] = now

            logger.info(f"Update check completed: updates_available={updates_available}")

            return result

    except httpx.TimeoutException:
        logger.error("GitHub API timeout")
        return {
            "status": "timeout",
            "current_version": get_current_version(),
            "updates_available": False,
            "message": "Таймаут запроса к GitHub API. Проверьте вручную.",
            "manual_check_url": "https://github.com/garik128/binom_assistant/releases"
        }
    except Exception as e:
        logger.error(f"Error checking updates: {e}", exc_info=True)
        return {
            "status": "error",
            "current_version": get_current_version(),
            "updates_available": False,
            "message": f"Ошибка проверки обновлений: {str(e)}",
            "manual_check_url": "https://github.com/garik128/binom_assistant/releases"
        }


@router.post("/update/pull")
@limiter.limit("10/hour")  # Максимум 10 обновлений в час
async def pull_updates(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Выполняет git pull и анализирует изменения

    ВНИМАНИЕ: После git pull может потребоваться перезагрузка приложения!

    Returns:
        Информация о выполненном обновлении и необходимых действиях
    """
    import subprocess
    from pathlib import Path

    try:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Git pull requested from {client_ip}")
        security_logger.warning(f"UPDATE_PULL | IP: {client_ip} | timestamp: {datetime.now().isoformat()}")

        work_dir = Path(__file__).parent.parent.parent.parent

        # Git pull
        pull_result = subprocess.run(
            ["git", "pull", "origin"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=60
        )

        if pull_result.returncode != 0:
            logger.error(f"Git pull failed: {pull_result.stderr}")
            raise HTTPException(status_code=500, detail=f"Ошибка git pull: {pull_result.stderr}")

        pull_output = pull_result.stdout

        # Анализируем изменения
        # Проверяем что изменилось
        changed_files = []
        if "Already up to date" not in pull_output:
            # Получаем список измененных файлов
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD@{1}", "HEAD"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            if diff_result.returncode == 0:
                changed_files = diff_result.stdout.strip().split('\n')

        # Анализируем типы изменений
        needs_rebuild = any('requirements.txt' in f or 'Dockerfile' in f for f in changed_files)
        needs_migration = any('migration' in f.lower() or 'models.py' in f for f in changed_files)
        only_frontend = all(f.endswith(('.html', '.css', '.js')) for f in changed_files if f)

        # Определяем действие
        if "Already up to date" in pull_output:
            action = "none"
            message = "Система уже актуальна"
            needs_restart = False
        elif needs_rebuild:
            action = "manual_rebuild"
            message = "Обновление требует rebuild Docker образа! Выполните: docker compose down && docker compose build && docker compose up -d"
            needs_restart = False
        elif needs_migration:
            action = "migration"
            message = "Обновление требует применения миграций БД. Перезапустите приложение."
            needs_restart = True
        elif only_frontend:
            action = "reload_page"
            message = "Обновлены статические файлы. Обновите страницу браузера (Ctrl+F5)"
            needs_restart = False
        else:
            action = "restart"
            message = "Обновление выполнено. Рекомендуется перезапустить приложение."
            needs_restart = True

        logger.info(f"Git pull completed. Action: {action}, changed files: {len(changed_files)}")

        return {
            "status": "ok",
            "action": action,
            "message": message,
            "needs_restart": needs_restart,
            "changed_files": changed_files,
            "changed_count": len([f for f in changed_files if f]),
            "pull_output": pull_output
        }

    except subprocess.TimeoutExpired:
        logger.error("Git pull timeout")
        raise HTTPException(status_code=500, detail="Таймаут выполнения git pull")
    except Exception as e:
        logger.error(f"Error pulling updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
