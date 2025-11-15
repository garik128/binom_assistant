"""
Инициализация и регистрация всех модулей при старте приложения
"""
import logging
from .registry import get_registry
from .critical_alerts.bleeding_detector import BleedingCampaignDetector
from .critical_alerts.zero_approval_alert import ZeroApprovalAlert
from .critical_alerts.spend_spike_monitor import SpendSpikeMonitor
from .critical_alerts.waste_campaign_finder import WasteCampaignFinder
from .critical_alerts.traffic_quality_crash import TrafficQualityCrash
from .critical_alerts.squeezed_offer import SqueezedOfferDetector
from .trend_analysis.microtrend_scanner import MicrotrendScanner
from .trend_analysis.momentum_tracker import MomentumTracker
from .trend_analysis.recovery_detector import RecoveryDetector
from .trend_analysis.acceleration_monitor import AccelerationMonitor
from .trend_analysis.trend_reversal_finder import TrendReversalFinder
from .stability.volatility_calculator import VolatilityCalculator
from .stability.consistency_scorer import ConsistencyScorer
from .stability.reliability_index import ReliabilityIndex
from .stability.performance_stability import PerformanceStability
from .predictive.roi_forecast import ROIForecast
from .predictive.profitability_horizon import ProfitabilityHorizon
from .predictive.approval_rate_predictor import ApprovalRatePredictor
from .predictive.campaign_lifecycle_stage import CampaignLifecycleStage
from .predictive.revenue_projection import RevenueProjection
from .problem_detection.sleepy_campaign_finder import SleepyCampaignFinder
from .problem_detection.cpl_margin_monitor import CPLMarginMonitor
from .problem_detection.conversion_drop_alert import ConversionDropAlert
from .problem_detection.approval_delay_impact import ApprovalDelayImpact
from .problem_detection.zombie_campaign_detector import ZombieCampaignDetector
from .problem_detection.source_fatigue_detector import SourceFatigueDetector
from .opportunities.hidden_gems_finder import HiddenGemsFinder
from .opportunities.sudden_winner_detector import SuddenWinnerDetector
from .opportunities.scaling_candidates import ScalingCandidates
from .opportunities.breakout_alert import BreakoutAlert
from .segmentation.smart_consolidator import SmartConsolidator
from .segmentation.performance_segmenter import PerformanceSegmenter
from .segmentation.source_group_matrix import SourceGroupMatrix
from .portfolio.portfolio_health_index import PortfolioHealthIndex
from .portfolio.total_performance_tracker import TotalPerformanceTracker
from .portfolio.risk_assessment import RiskAssessment
from .portfolio.diversification_score import DiversificationScore
from .portfolio.budget_optimizer import BudgetOptimizer
from .sources_offers.network_performance_monitor import NetworkPerformanceMonitor
from .sources_offers.source_quality_scorer import SourceQualityScorer
from .sources_offers.offer_profitability_ranker import OfferProfitabilityRanker

from .sources_offers.offer_lifecycle_tracker import OfferLifecycleTracker
logger = logging.getLogger(__name__)


def register_all_modules():
    """
    Регистрирует все доступные модули в реестре.

    Вызывается при старте приложения.
    """
    registry = get_registry()

    # Регистрируем модули критических алертов
    registry.register(BleedingCampaignDetector)
    registry.register(ZeroApprovalAlert)
    registry.register(SpendSpikeMonitor)
    registry.register(WasteCampaignFinder)
    registry.register(TrafficQualityCrash)
    registry.register(SqueezedOfferDetector)

    # Регистрируем модули анализа трендов
    registry.register(MicrotrendScanner)
    registry.register(MomentumTracker)
    registry.register(RecoveryDetector)
    registry.register(AccelerationMonitor)
    registry.register(TrendReversalFinder)

    # Регистрируем модули оценки стабильности
    registry.register(VolatilityCalculator)
    registry.register(ConsistencyScorer)
    registry.register(ReliabilityIndex)
    registry.register(PerformanceStability)

    # Регистрируем модули предиктивной аналитики
    registry.register(ROIForecast)
    registry.register(ProfitabilityHorizon)
    registry.register(ApprovalRatePredictor)
    registry.register(CampaignLifecycleStage)
    registry.register(RevenueProjection)

    # Регистрируем модули обнаружения проблем
    registry.register(SleepyCampaignFinder)
    registry.register(CPLMarginMonitor)
    registry.register(ConversionDropAlert)
    registry.register(ApprovalDelayImpact)
    registry.register(ZombieCampaignDetector)
    registry.register(SourceFatigueDetector)

    # Регистрируем модули поиска возможностей
    registry.register(HiddenGemsFinder)
    registry.register(SuddenWinnerDetector)
    registry.register(ScalingCandidates)
    registry.register(BreakoutAlert)

    # Регистрируем модули группировки и сегментации
    registry.register(SmartConsolidator)
    registry.register(PerformanceSegmenter)
    registry.register(SourceGroupMatrix)

    # Регистрируем модули портфеля
    registry.register(PortfolioHealthIndex)
    registry.register(TotalPerformanceTracker)
    registry.register(RiskAssessment)
    registry.register(DiversificationScore)
    registry.register(BudgetOptimizer)

    # Регистрируем модули источников и офферов
    registry.register(NetworkPerformanceMonitor)
    registry.register(SourceQualityScorer)
    registry.register(OfferProfitabilityRanker)
    registry.register(OfferLifecycleTracker)

    # TODO: Добавить регистрацию остальных модулей по мере их создания
    # ...

    logger.info(f"Registered {registry.get_count()} modules")

    # Логируем категории
    categories = registry.list_categories()
    logger.info(f"Available categories: {', '.join(categories)}")


def check_and_run_initial_collection():
    """
    Проверяет, является ли это первым запуском, и запускает начальный сбор данных.

    Использует app_settings для отслеживания состояния первого запуска.
    При первом запуске собирает данные за 60 дней в фоновом режиме.
    """
    try:
        from services.settings_manager import get_settings_manager
        from storage.database import session_scope, BackgroundTask
        from datetime import datetime
        import threading

        settings = get_settings_manager()

        # Проверяем флаг first_run
        first_run = settings.get('system.first_run', default='true')

        if first_run.lower() == 'true':
            logger.info("=" * 60)
            logger.info("FIRST RUN DETECTED - Starting initial data collection")
            logger.info("Collecting 60 days of data from Binom...")
            logger.info("This may take 10-15 minutes depending on data volume")
            logger.info("=" * 60)

            # Создаем задачу в БД
            try:
                with session_scope() as session:
                    task = BackgroundTask(
                        task_type='initial_collection',
                        status='pending',
                        progress=0,
                        progress_message='Подготовка к первичному сбору данных за 60 дней',
                        created_at=datetime.utcnow()
                    )
                    session.add(task)
                    session.commit()
                    task_id = task.id
                    logger.info(f"Created background task #{task_id} for initial collection")
            except Exception as e:
                logger.error(f"Failed to create background task: {e}")
                task_id = None

            # Запускаем сбор данных в отдельном потоке
            def run_initial_collection():
                try:
                    from services.scheduler.collector import DataCollector

                    # Обновляем статус задачи
                    if task_id:
                        with session_scope() as session:
                            task = session.query(BackgroundTask).filter_by(id=task_id).first()
                            if task:
                                task.status = 'running'
                                task.started_at = datetime.utcnow()
                                task.progress_message = 'Запуск сборщика данных...'
                                session.commit()

                    # Создаем collector с отключением пауз для быстрого сбора
                    collector = DataCollector(skip_pauses=True)
                    logger.info("Starting initial collection (60 days, fast mode)...")

                    # Запускаем сбор за 60 дней
                    result = collector.initial_collect(days=60)

                    # Обновляем статус на успех
                    if task_id:
                        with session_scope() as session:
                            task = session.query(BackgroundTask).filter_by(id=task_id).first()
                            if task:
                                task.status = 'completed'
                                task.progress = 100
                                task.progress_message = 'Первичный сбор данных завершен'
                                task.completed_at = datetime.utcnow()
                                task.result = result
                                session.commit()

                    logger.info("=" * 60)
                    logger.info("INITIAL DATA COLLECTION COMPLETED SUCCESSFULLY")
                    logger.info(f"Collected data: {result}")
                    logger.info("=" * 60)

                    # Пересчитываем stat_periods (7days, 14days, 30days) для дашборда
                    try:
                        from services.scheduler.aggregate_periods import recalculate_stat_periods
                        logger.info("Recalculating stat_periods for dashboard...")
                        periods_result = recalculate_stat_periods()
                        logger.info(f"Stat_periods recalculated: {periods_result['records_created']} created, "
                                   f"{periods_result['records_updated']} updated, "
                                   f"{periods_result['campaigns_processed']} campaigns")
                    except Exception as periods_error:
                        logger.error(f"Failed to recalculate stat_periods: {periods_error}", exc_info=True)
                        # Не критично, продолжаем

                    # Отмечаем что первый запуск выполнен
                    settings.set('system.first_run', 'false')
                    logger.info("First run flag set to false")

                    # Запускаем scheduler'ы после успешного первичного сбора
                    try:
                        logger.info("Starting schedulers after initial collection...")

                        # 1. Запускаем TaskScheduler (data collector)
                        from services.scheduler.scheduler import TaskScheduler
                        task_scheduler = TaskScheduler()
                        task_scheduler.setup_jobs()
                        task_scheduler.start()
                        logger.info("TaskScheduler started successfully")

                        # 2. Запускаем ModuleScheduler
                        from .module_scheduler import get_module_scheduler
                        module_scheduler = get_module_scheduler()
                        module_scheduler.setup_module_jobs()
                        module_scheduler.start()
                        logger.info("Module scheduler started successfully")

                        logger.info("All schedulers started after initial collection")
                    except Exception as sched_error:
                        logger.error(f"Failed to start schedulers after initial collection: {sched_error}")

                except Exception as e:
                    logger.error(f"Initial collection failed: {e}", exc_info=True)

                    # Обновляем статус на ошибку
                    if task_id:
                        try:
                            with session_scope() as session:
                                task = session.query(BackgroundTask).filter_by(id=task_id).first()
                                if task:
                                    task.status = 'failed'
                                    task.progress_message = 'Ошибка при первичном сборе данных'
                                    task.error = str(e)
                                    task.completed_at = datetime.utcnow()
                                    session.commit()
                        except Exception as db_error:
                            logger.error(f"Failed to update task status: {db_error}")

            # Запускаем в фоновом потоке
            thread = threading.Thread(target=run_initial_collection, daemon=True)
            thread.start()
            logger.info("Initial collection started in background thread")
        else:
            logger.info("Not first run, skipping initial collection")

    except Exception as e:
        logger.error(f"Failed to check/run initial collection: {e}", exc_info=True)


def init_modules():
    """
    Инициализирует систему модулей.

    Вызывает:
    - Регистрацию всех модулей
    - Создание таблиц БД (если нужно)
    - Загрузку конфигураций из БД
    - Запуск планировщика автозапуска модулей
    - Проверку первого запуска и начальный сбор данных
    """
    logger.info("Initializing modules system...")

    # Регистрируем модули
    register_all_modules()

    # Создаем таблицы БД (если они еще не созданы)
    try:
        from storage.database.base import create_tables
        create_tables()
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.warning(f"Could not create tables (may already exist): {e}")

    # Проверяем first_run перед запуском планировщика модулей
    try:
        from services.settings_manager import get_settings_manager
        settings = get_settings_manager()
        first_run = settings.get('system.first_run', default='true')

        if first_run.lower() != 'true':
            # Запускаем планировщик модулей только если НЕ first run
            from .module_scheduler import get_module_scheduler
            scheduler = get_module_scheduler()
            scheduler.setup_module_jobs()
            scheduler.start()
            logger.info("Module scheduler started")
        else:
            logger.warning("First run detected - module scheduler will start after initial collection")
    except Exception as e:
        logger.error(f"Failed to check/start module scheduler: {e}")

    # Проверяем первый запуск и запускаем начальный сбор данных
    try:
        check_and_run_initial_collection()
    except Exception as e:
        logger.error(f"Failed to check initial collection: {e}")

    logger.info("Modules system initialized successfully")


def shutdown_modules():
    """
    Останавливает систему модулей при shutdown приложения.

    Вызывает:
    - Остановку планировщика модулей
    """
    logger.info("Shutting down modules system...")

    try:
        from .module_scheduler import get_module_scheduler
        scheduler = get_module_scheduler()
        scheduler.stop()
        logger.info("Module scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping module scheduler: {e}")

    logger.info("Modules system shutdown complete")
