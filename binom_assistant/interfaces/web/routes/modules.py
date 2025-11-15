# -*- coding: utf-8 -*-
"""
API endpoints для модулей аналитики
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from ..dependencies import get_db
from ..auth import get_current_user, get_current_user_or_internal
from ..schemas.module import (
    ModuleListResponse,
    ModuleInfoResponse,
    ModuleResultResponse,
    ModuleRunHistoryResponse,
    ModuleRunHistoryItem,
    ModuleConfigUpdate,
    ModuleRunRequest,
    ModuleMetadataResponse,
    ModuleConfigResponse
)
from modules import ModuleRegistry, ModuleRunner, ModuleConfig
from storage.database.models import (
    ModuleConfig as ModuleConfigDB,
    ModuleRun as ModuleRunDB
)
import logging

logger = logging.getLogger(__name__)

# Основной роутер с авторизацией для всех эндпоинтов
router = APIRouter(dependencies=[Depends(get_current_user)])

# Отдельный роутер для эндпоинта /run без обязательной авторизации (для AI агента)
run_router = APIRouter()


def get_module_registry() -> ModuleRegistry:
    """Получает глобальный реестр модулей"""
    from modules.registry import get_registry
    return get_registry()


def get_module_runner() -> ModuleRunner:
    """Создает новый экземпляр раннера"""
    return ModuleRunner()


@router.get("/modules", response_model=ModuleListResponse)
async def list_modules(
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    db: Session = Depends(get_db),
    registry: ModuleRegistry = Depends(get_module_registry)
):
    """
    Получает список всех доступных модулей.

    Args:
        category: Фильтр по категории (опционально)
        db: Сессия БД
        registry: Реестр модулей

    Returns:
        Список модулей с метаданными + конфигом + последний запуск
    """
    try:
        if category:
            modules_list = registry.list_by_category(category)
        else:
            modules_list = registry.list_modules()

        categories = registry.list_categories()

        # Обогащаем данные из БД
        enriched_modules = []
        for module_meta in modules_list:
            module_data = module_meta.model_dump()

            # Получаем конфигурацию из БД
            config = db.query(ModuleConfigDB).filter(
                ModuleConfigDB.module_id == module_meta.id
            ).first()

            if config:
                # Модуль считается включенным если у него есть schedule
                module_data['enabled'] = bool(config.schedule and config.schedule.strip())
            else:
                # Для новых модулей проверяем дефолтный конфиг
                module = registry.get_module_instance(module_meta.id)
                if module:
                    default_config = module.get_default_config()
                    module_data['enabled'] = bool(default_config.schedule and default_config.schedule.strip())

            # Получаем последний запуск
            last_run = db.query(ModuleRunDB).filter(
                ModuleRunDB.module_id == module_meta.id
            ).order_by(ModuleRunDB.started_at.desc()).first()

            if last_run:
                module_data['last_run'] = last_run.completed_at or last_run.started_at
                module_data['status'] = last_run.status
                if last_run.results:
                    # Берем только summary для списка
                    module_data['last_result'] = {
                        'summary': last_run.results.get('data', {}).get('summary')
                    }

            enriched_modules.append(ModuleMetadataResponse(**module_data))

        return ModuleListResponse(
            modules=enriched_modules,
            total=len(enriched_modules),
            categories=categories
        )

    except Exception as e:
        logger.error(f"Error listing modules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/modules/{module_id}", response_model=ModuleInfoResponse)
async def get_module_info(
    module_id: str,
    db: Session = Depends(get_db),
    registry: ModuleRegistry = Depends(get_module_registry)
):
    """
    Получает информацию о модуле.

    Args:
        module_id: ID модуля
        db: Сессия БД
        registry: Реестр модулей

    Returns:
        Информация о модуле (метаданные + конфигурация)
    """
    try:
        # Проверяем что модуль существует
        module = registry.get_module_instance(module_id)
        if not module:
            raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

        # Загружаем конфигурацию из БД
        db_config = db.query(ModuleConfigDB).filter(
            ModuleConfigDB.module_id == module_id
        ).first()

        if db_config:
            config = ModuleConfigResponse(
                enabled=db_config.enabled,
                schedule=db_config.schedule,
                alerts_enabled=getattr(db_config, 'alerts_enabled', False),
                timeout_seconds=db_config.timeout_seconds,
                cache_ttl_seconds=db_config.cache_ttl_seconds,
                params=db_config.params or {}
            )
        else:
            # Используем конфиг по умолчанию
            default_config = module.config
            config = ModuleConfigResponse(
                enabled=default_config.enabled,
                schedule=default_config.schedule,
                alerts_enabled=getattr(default_config, 'alerts_enabled', False),
                timeout_seconds=default_config.timeout_seconds,
                cache_ttl_seconds=default_config.cache_ttl_seconds,
                params=default_config.params
            )

        # Получаем метаданные параметров если модуль их поддерживает
        param_metadata = {}
        logger.info(f"Checking param_metadata for module '{module_id}', has method: {hasattr(module, 'get_param_metadata')}")
        if hasattr(module, 'get_param_metadata'):
            try:
                result = module.get_param_metadata()
                if result:
                    param_metadata = result
                logger.info(f"Got param_metadata for '{module_id}': {list(param_metadata.keys())}")
            except Exception as e:
                logger.warning(f"Failed to get param_metadata for module '{module_id}': {e}")

        # Получаем метаданные severity если модуль их поддерживает
        severity_metadata = {}
        if hasattr(module, 'get_severity_metadata'):
            try:
                result = module.get_severity_metadata()
                if result:
                    severity_metadata = result
                logger.info(f"Got severity_metadata for '{module_id}': enabled={severity_metadata.get('enabled', False)}")
            except Exception as e:
                logger.warning(f"Failed to get severity_metadata for module '{module_id}': {e}")

        # Формируем метаданные с правильным enabled (на основе schedule)
        metadata_dict = module.metadata.model_dump()
        metadata_dict['enabled'] = bool(config.schedule and config.schedule.strip())

        return ModuleInfoResponse(
            metadata=ModuleMetadataResponse(**metadata_dict),
            config=config,
            param_metadata=param_metadata,
            severity_metadata=severity_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting module info for '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/modules/{module_id}/config/default", response_model=ModuleConfigResponse)
async def get_module_default_config(
    module_id: str,
    registry: ModuleRegistry = Depends(get_module_registry)
):
    """
    Получает дефолтную конфигурацию модуля.

    Args:
        module_id: ID модуля
        registry: Реестр модулей

    Returns:
        Дефолтная конфигурация модуля
    """
    try:
        # Проверяем что модуль существует
        module = registry.get_module_instance(module_id)
        if not module:
            raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

        # Получаем дефолтную конфигурацию из модуля
        default_config = module.get_default_config()

        return ModuleConfigResponse(
            enabled=default_config.enabled,
            schedule=default_config.schedule,
            timeout_seconds=default_config.timeout_seconds,
            cache_ttl_seconds=default_config.cache_ttl_seconds,
            params=default_config.params
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default config for module '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@run_router.post("/modules/{module_id}/run", response_model=ModuleResultResponse)
async def run_module(
    module_id: str,
    request: ModuleRunRequest,
    runner: ModuleRunner = Depends(get_module_runner),
    user: str = Depends(get_current_user_or_internal)
):
    """
    Запускает модуль на выполнение.
    Разрешает вызовы без токена для внутренних запросов (AI агент).

    Args:
        module_id: ID модуля
        request: Параметры запуска
        runner: Раннер модулей
        user: Username или "internal" для внутренних вызовов

    Returns:
        Результат выполнения модуля
    """
    try:
        # Создаем конфигурацию если переданы параметры
        config = None
        if request.params:
            # Получаем базовый конфиг модуля
            module = runner.registry.get_module_instance(module_id)
            if not module:
                raise ValueError(f"Module '{module_id}' not found")

            # Загружаем сохраненный конфиг из БД или берем дефолтный
            base_config = runner._load_config(module_id) or module.get_default_config()

            # Сливаем параметры: базовые + пользовательские
            merged_params = {**base_config.params, **request.params}

            # Создаем новый конфиг со слитыми параметрами
            config = ModuleConfig(
                enabled=base_config.enabled,
                schedule=base_config.schedule,
                alerts_enabled=base_config.alerts_enabled,
                timeout_seconds=base_config.timeout_seconds,
                cache_ttl_seconds=base_config.cache_ttl_seconds,
                params=merged_params
            )

        # Запускаем модуль
        result = runner.run_module(
            module_id=module_id,
            config=config,
            use_cache=request.use_cache
        )

        return ModuleResultResponse(**result.model_dump())

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error running module '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/modules/{module_id}/results", response_model=ModuleResultResponse)
async def get_module_results(
    module_id: str,
    db: Session = Depends(get_db)
):
    """
    Получает результаты последнего запуска модуля.

    Args:
        module_id: ID модуля
        db: Сессия БД

    Returns:
        Результат последнего успешного запуска
    """
    try:
        # Ищем последний успешный запуск
        last_run = db.query(ModuleRunDB).filter(
            ModuleRunDB.module_id == module_id,
            ModuleRunDB.status == "success"
        ).order_by(ModuleRunDB.completed_at.desc()).first()

        if not last_run or not last_run.results:
            raise HTTPException(
                status_code=404,
                detail=f"No successful runs found for module '{module_id}'"
            )

        # Add params from run to results
        result_data = last_run.results.copy()
        result_data['params'] = last_run.params
        return ModuleResultResponse(**result_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting results for module '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/modules/{module_id}/history", response_model=ModuleRunHistoryResponse)
async def get_module_history(
    module_id: str,
    limit: int = Query(10, description="Количество записей"),
    db: Session = Depends(get_db)
):
    """
    Получает историю запусков модуля.

    Args:
        module_id: ID модуля
        limit: Количество записей
        db: Сессия БД

    Returns:
        История запусков
    """
    try:
        runs = db.query(ModuleRunDB).filter(
            ModuleRunDB.module_id == module_id
        ).order_by(ModuleRunDB.started_at.desc()).limit(limit).all()

        history_items = []
        for run in runs:
            # Генерируем краткую сводку из results
            summary = None
            if run.status == "success" and run.results:
                try:
                    data = run.results.get("data", {})
                    summary_data = data.get("summary", {})

                    # Формируем специфичные сводки для каждого модуля
                    # critical_alerts
                    if run.module_id == "bleeding_detector":
                        total_found = summary_data.get("total_found", 0)
                        total_losses = summary_data.get("total_losses", 0)
                        summary = f"Найдено: {total_found}, Убытки: ${total_losses:.2f}"
                    elif run.module_id == "waste_campaign_finder":
                        total_found = summary_data.get("total_found", 0)
                        total_wasted = summary_data.get("total_wasted", 0)
                        summary = f"Найдено: {total_found}, Убытки: ${total_wasted:.2f}"
                    elif run.module_id == "zero_approval_alert":
                        total_found = summary_data.get("total_found", 0)
                        total_pending_leads = summary_data.get("total_pending_leads", 0)
                        summary = f"Найдено: {total_found}, Лидов на холде: {total_pending_leads}"
                    elif run.module_id == "spend_spike_monitor":
                        total_found = summary_data.get("total_found", 0)
                        total_extra = summary_data.get("total_extra_spend", 0)
                        summary = f"Найдено: {total_found}, Излишки: ${total_extra:.2f}"
                    elif run.module_id == "traffic_quality_crash":
                        total_found = summary_data.get("total_found", 0)
                        avg_cr_drop = summary_data.get("avg_cr_drop", 0)
                        summary = f"Найдено: {total_found}, Ср. падение CR: {avg_cr_drop:.1f}%"
                    elif run.module_id == "squeezed_offer":
                        total_found = summary_data.get("total_found", 0)
                        avg_cr_drop = summary_data.get("avg_cr_drop", 0)
                        summary = f"Найдено: {total_found}, Ср. падение CR: {avg_cr_drop:.1f}%"

                    # trend_analysis
                    elif run.module_id == "microtrend_scanner":
                        total_pos = summary_data.get("total_positive", 0)
                        total_neg = summary_data.get("total_negative", 0)
                        summary = f"Растут: {total_pos}, Падают: {total_neg}"
                    elif run.module_id == "momentum_tracker":
                        accel = summary_data.get("total_accelerating", 0)
                        decel = summary_data.get("total_decelerating", 0)
                        summary = f"Ускоряются: {accel}, Замедляются: {decel}"
                    elif run.module_id == "recovery_detector":
                        recovering = summary_data.get("total_recovering", 0)
                        strong = summary_data.get("strong_recoveries", 0)
                        summary = f"Восстанавливаются: {recovering}, Сильных: {strong}"
                    elif run.module_id == "acceleration_monitor":
                        accel = summary_data.get("total_accelerating", 0)
                        decel = summary_data.get("total_decelerating", 0)
                        summary = f"Ускоряются: {accel}, Замедляются: {decel}"
                    elif run.module_id == "trend_reversal_finder":
                        total_reversals = summary_data.get("total_reversals", 0)
                        critical = summary_data.get("critical_reversals", 0)
                        summary = f"Развороты: {total_reversals}, Критичных: {critical}"

                    # problem_detection
                    elif run.module_id == "sleepy_campaign_finder":
                        total_sleepy = summary_data.get("total_sleepy", 0)
                        critical = summary_data.get("critical_count", 0)
                        summary = f"Спящих: {total_sleepy}, Критичных: {critical}"
                    elif run.module_id == "cpl_margin_monitor":
                        total_problems = summary_data.get("total_problems", 0)
                        critical = summary_data.get("critical_count", 0)
                        summary = f"Проблем: {total_problems}, Критичных: {critical}"
                    elif run.module_id == "conversion_drop_alert":
                        total_problems = summary_data.get("total_problems", 0)
                        critical = summary_data.get("critical_count", 0)
                        summary = f"Падений CR: {total_problems}, Критичных: {critical}"
                    elif run.module_id == "approval_delay_impact":
                        total_problems = summary_data.get("total_problems", 0)
                        avg_delay = summary_data.get("avg_delay_overall", 0)
                        summary = f"Проблем: {total_problems}, Ср. задержка: {avg_delay:.1f}ч"
                    elif run.module_id == "zombie_campaign_detector":
                        total_problems = summary_data.get("total_problems", 0)
                        total_wasted = summary_data.get("total_wasted", 0)
                        summary = f"Зомби: {total_problems}, Убытки: ${total_wasted:.2f}"
                    elif run.module_id == "source_fatigue_detector":
                        total_problems = summary_data.get("total_problems", 0)
                        critical = summary_data.get("critical_count", 0)
                        summary = f"Выгоревших: {total_problems}, Критичных: {critical}"

                    # opportunities
                    elif run.module_id == "hidden_gems_finder":
                        total_gems = summary_data.get("total_gems", 0)
                        high_pot = summary_data.get("high_potential", 0)
                        summary = f"Алмазов: {total_gems}, Высокий потенциал: {high_pot}"
                    elif run.module_id == "sudden_winner_detector":
                        total_winners = summary_data.get("total_winners", 0)
                        roi_surge = summary_data.get("roi_surge", 0)
                        summary = f"Победителей: {total_winners}, ROI всплесков: {roi_surge}"
                    elif run.module_id == "scaling_candidates":
                        total_cand = summary_data.get("total_candidates", 0)
                        avg_roi = summary_data.get("avg_roi", 0)
                        summary = f"Кандидатов на скейл: {total_cand}, Ср. ROI: {avg_roi:.1f}%"
                    elif run.module_id == "breakout_alert":
                        total_breakouts = summary_data.get("total_breakouts", 0)
                        avg_roi_growth = summary_data.get("avg_roi_growth", 0)
                        summary = f"Прорывов: {total_breakouts}, Ср. рост ROI: {avg_roi_growth:.1f}%"

                    # segmentation
                    elif run.module_id == "smart_consolidator":
                        total_clusters = summary_data.get("total_clusters", 0)
                        total_campaigns = summary_data.get("total_campaigns", 0)
                        summary = f"Кластеров: {total_clusters}, Кампаний: {total_campaigns}"
                    elif run.module_id == "performance_segmenter":
                        stars = summary_data.get("stars_count", 0)
                        performers = summary_data.get("performers_count", 0)
                        summary = f"Звезд: {stars}, Хорошо работает: {performers}"
                    elif run.module_id == "source_group_matrix":
                        total_cells = summary_data.get("total_cells", 0)
                        profitable = summary_data.get("profitable_cells", 0)
                        summary = f"Ячеек: {total_cells}, Прибыльных: {profitable}"

                    # portfolio
                    elif run.module_id == "diversification_score":
                        total_campaigns = summary_data.get("total_campaigns", 0)
                        unique_sources = summary_data.get("unique_sources", 0)
                        summary = f"Кампаний: {total_campaigns}, Источников: {unique_sources}"
                    elif run.module_id == "risk_assessment":
                        total_campaigns = summary_data.get("total_campaigns", 0)
                        roi_std = summary_data.get("roi_std_dev", 0)
                        summary = f"Кампаний: {total_campaigns}, Волатильность ROI: {roi_std:.1f}%"
                    elif run.module_id == "total_performance_tracker":
                        total_revenue = summary_data.get("total_revenue", 0)
                        roi = summary_data.get("roi", 0)
                        summary = f"Доход: ${total_revenue:.2f}, ROI: {roi:.1f}%"
                    elif run.module_id == "portfolio_health_index":
                        total_campaigns = summary_data.get("total_campaigns", 0)
                        profitable = summary_data.get("profitable_campaigns", 0)
                        summary = f"Кампаний: {total_campaigns}, Прибыльных: {profitable}"
                    elif run.module_id == "budget_optimizer":
                        total_campaigns = summary_data.get("total_campaigns", 0)
                        top_campaigns = summary_data.get("top_campaigns", 0)
                        summary = f"Кампаний: {total_campaigns}, Топовых: {top_campaigns}"

                    # sources_offers
                    elif run.module_id == "source_quality_scorer":
                        total_sources = summary_data.get("total_sources", 0)
                        excellent = summary_data.get("excellent_count", 0)
                        summary = f"Источников: {total_sources}, Отличных: {excellent}"
                    elif run.module_id == "network_performance_monitor":
                        total_networks = summary_data.get("total_networks", 0)
                        avg_score = summary_data.get("avg_performance_score", 0)
                        summary = f"Сетей: {total_networks}, Ср. оценка: {avg_score:.1f}"
                    elif run.module_id == "offer_profitability_ranker":
                        total_offers = summary_data.get("total_offers", 0)
                        avg_roi = summary_data.get("avg_roi_portfolio", 0)
                        summary = f"Офферов: {total_offers}, Ср. ROI: {avg_roi:.1f}%"
                    elif run.module_id == "offer_lifecycle_tracker":
                        total_offers = summary_data.get("total_offers", 0)
                        summary = f"Офферов: {total_offers}"

                    # stability
                    elif run.module_id == "consistency_scorer":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        total_high = summary_data.get("total_high", 0)
                        summary = f"Проанализировано: {total_analyzed}, Высокая стабильность: {total_high}"
                    elif run.module_id == "performance_stability":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        total_high = summary_data.get("total_high", 0)
                        summary = f"Проанализировано: {total_analyzed}, Высокая стабильность: {total_high}"
                    elif run.module_id == "reliability_index":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        total_high = summary_data.get("total_high", 0)
                        summary = f"Проанализировано: {total_analyzed}, Высокая надежность: {total_high}"
                    elif run.module_id == "volatility_calculator":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        total_low = summary_data.get("total_low", 0)
                        summary = f"Проанализировано: {total_analyzed}, Низкая волатильность: {total_low}"

                    # predictive
                    elif run.module_id == "roi_forecast":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        improving = summary_data.get("improving_count", 0)
                        summary = f"Проанализировано: {total_analyzed}, Улучшается: {improving}"
                    elif run.module_id == "profitability_horizon":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        breakeven = summary_data.get("breakeven_forecasts", 0)
                        summary = f"Проанализировано: {total_analyzed}, Прогноз окупаемости: {breakeven}"
                    elif run.module_id == "approval_rate_predictor":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        improving = summary_data.get("improving_count", 0)
                        summary = f"Проанализировано: {total_analyzed}, Улучшается: {improving}"
                    elif run.module_id == "campaign_lifecycle_stage":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        growth = summary_data.get("growth_count", 0)
                        summary = f"Проанализировано: {total_analyzed}, Растут: {growth}"
                    elif run.module_id == "revenue_projection":
                        total_analyzed = summary_data.get("total_analyzed", 0)
                        increasing = summary_data.get("increasing_count", 0)
                        summary = f"Проанализировано: {total_analyzed}, Растет доход: {increasing}"
                    else:
                        # Fallback для новых модулей
                        total_found = summary_data.get("total_found", summary_data.get("total_analyzed", 0))
                        if total_found > 0:
                            summary = f"Найдено: {total_found}"
                        else:
                            summary = "Успешно выполнен"
                except Exception:
                    summary = "Успешно выполнен"
            elif run.status == "error":
                summary = run.error[:50] if run.error else "Ошибка выполнения"

            history_items.append(ModuleRunHistoryItem(
                id=run.id,
                module_id=run.module_id,
                started_at=run.started_at,
                completed_at=run.completed_at,
                status=run.status,
                execution_time_ms=run.execution_time_ms,
                error=run.error,
                summary=summary,
                params=run.params
            ))

        total = db.query(ModuleRunDB).filter(
            ModuleRunDB.module_id == module_id
        ).count()

        return ModuleRunHistoryResponse(
            runs=history_items,
            total=total
        )

    except Exception as e:
        logger.error(f"Error getting history for module '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/modules/{module_id}/history/{run_id}")
async def get_module_run(
    module_id: str,
    run_id: int,
    db: Session = Depends(get_db)
):
    """
    Получает конкретный запуск модуля с результатами.

    Args:
        module_id: ID модуля
        run_id: ID запуска
        db: Сессия БД

    Returns:
        Информация о запуске с результатами
    """
    try:
        run = db.query(ModuleRunDB).filter(
            ModuleRunDB.id == run_id,
            ModuleRunDB.module_id == module_id
        ).first()

        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        return {
            "id": run.id,
            "module_id": run.module_id,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "status": run.status,
            "params": run.params,
            "execution_time_ms": run.execution_time_ms,
            "error": run.error,
            "results": run.results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/modules/{module_id}/history/{run_id}")
async def delete_module_run(
    module_id: str,
    run_id: int,
    db: Session = Depends(get_db)
):
    """
    Удаляет конкретную запись из истории.

    Args:
        module_id: ID модуля
        run_id: ID запуска
        db: Сессия БД

    Returns:
        Сообщение об успехе
    """
    try:
        run = db.query(ModuleRunDB).filter(
            ModuleRunDB.id == run_id,
            ModuleRunDB.module_id == module_id
        ).first()

        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        db.delete(run)
        db.commit()

        return {"message": "Run deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting run {run_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/modules/{module_id}/history")
async def delete_module_history(
    module_id: str,
    db: Session = Depends(get_db)
):
    """
    Удаляет всю историю запусков модуля.

    Args:
        module_id: ID модуля
        db: Сессия БД

    Returns:
        Количество удаленных записей
    """
    try:
        count = db.query(ModuleRunDB).filter(
            ModuleRunDB.module_id == module_id
        ).delete()

        db.commit()

        return {"message": f"Deleted {count} history records", "count": count}

    except Exception as e:
        logger.error(f"Error deleting history for module '{module_id}': {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/modules/{module_id}/config")
async def update_module_config(
    module_id: str,
    config_update: ModuleConfigUpdate,
    db: Session = Depends(get_db),
    registry: ModuleRegistry = Depends(get_module_registry)
):
    """
    Обновляет конфигурацию модуля.

    Args:
        module_id: ID модуля
        config_update: Обновления конфигурации
        db: Сессия БД
        registry: Реестр модулей

    Returns:
        Обновленная конфигурация
    """
    try:
        # Проверяем что модуль существует
        module = registry.get_module_instance(module_id)
        if not module:
            raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")

        # Ищем существующую конфигурацию
        db_config = db.query(ModuleConfigDB).filter(
            ModuleConfigDB.module_id == module_id
        ).first()

        if db_config:
            # Обновляем существующую
            if config_update.enabled is not None:
                db_config.enabled = config_update.enabled
            if config_update.schedule is not None:
                db_config.schedule = config_update.schedule
            if config_update.alerts_enabled is not None:
                db_config.alerts_enabled = config_update.alerts_enabled
            if config_update.timeout_seconds is not None:
                db_config.timeout_seconds = config_update.timeout_seconds
            if config_update.cache_ttl_seconds is not None:
                db_config.cache_ttl_seconds = config_update.cache_ttl_seconds
            if config_update.params is not None:
                db_config.params = config_update.params

            db_config.updated_at = datetime.utcnow()
        else:
            # Создаем новую
            default_config = module.config
            db_config = ModuleConfigDB(
                module_id=module_id,
                enabled=config_update.enabled if config_update.enabled is not None else default_config.enabled,
                schedule=config_update.schedule or default_config.schedule,
                alerts_enabled=config_update.alerts_enabled if config_update.alerts_enabled is not None else getattr(default_config, 'alerts_enabled', False),
                timeout_seconds=config_update.timeout_seconds or default_config.timeout_seconds,
                cache_ttl_seconds=config_update.cache_ttl_seconds or default_config.cache_ttl_seconds,
                params=config_update.params or default_config.params
            )
            db.add(db_config)

        db.commit()

        # Обновляем задачу в планировщике
        try:
            from modules.module_scheduler import get_module_scheduler
            scheduler = get_module_scheduler()
            scheduler.update_module_job(
                module_id=module_id,
                enabled=db_config.enabled,
                schedule=db_config.schedule,
                params=db_config.params
            )
            logger.info(f"Scheduler updated for module '{module_id}'")
        except Exception as e:
            logger.warning(f"Could not update scheduler for module '{module_id}': {e}")

        return {
            "status": "success",
            "message": f"Configuration for module '{module_id}' updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating config for module '{module_id}': {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/modules/{module_id}/cache")
async def clear_module_cache(
    module_id: str,
    runner: ModuleRunner = Depends(get_module_runner)
):
    """
    Очищает кэш модуля.

    Args:
        module_id: ID модуля
        runner: Раннер модулей

    Returns:
        Статус операции
    """
    try:
        count = runner.clear_cache(module_id)

        return {
            "status": "success",
            "message": f"Cleared {count} cache entries for module '{module_id}'"
        }

    except Exception as e:
        logger.error(f"Error clearing cache for module '{module_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
