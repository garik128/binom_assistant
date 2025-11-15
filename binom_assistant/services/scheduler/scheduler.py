"""
Планировщик задач

Использует APScheduler для выполнения задач по расписанию:
- Ежедневный сбор данных в 3:00
- Недельная агрегация по понедельникам
- Поиск проблемных кампаний
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from .collector import DataCollector
from .cleanup import cleanup_old_data
from .aggregate_periods import recalculate_stat_periods
from core.data_processor import aggregate_weekly_stats
from config import get_config
from utils import get_now


logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Планировщик задач

    Использование:
        scheduler = TaskScheduler()
        scheduler.start()
        # ... работа приложения ...
        scheduler.stop()
    """

    def __init__(self):
        """Инициализация планировщика"""
        config = get_config()
        timezone_str = config.timezone
        self.scheduler = BackgroundScheduler(timezone=timezone_str)
        self.collector = DataCollector()

        # Добавляем обработчики событий
        self.scheduler.add_listener(
            self._job_executed,
            EVENT_JOB_EXECUTED
        )
        self.scheduler.add_listener(
            self._job_error,
            EVENT_JOB_ERROR
        )

        logger.info(f"TaskScheduler initialized with timezone: {timezone_str}")

    def setup_jobs(self):
        """
        Настраивает все задачи

        ВАЖНО: вызывай перед start()
        """
        logger.info("Setting up scheduled jobs...")

        # Загружаем расписания из настроек
        from services.settings_manager import get_settings_manager
        settings_mgr = get_settings_manager()

        # 1. Ежедневный сбор данных - читаем расписание из БД
        daily_stats_cron = settings_mgr.get('schedule.daily_stats', default='0 * * * *')  # по умолчанию каждый час
        logger.info(f"Daily stats schedule from settings: {daily_stats_cron}")

        self.scheduler.add_job(
            func=self._daily_collection_job,
            trigger=CronTrigger.from_crontab(daily_stats_cron),
            id='daily_collection',
            name='Daily Data Collection',
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=1800  # может опоздать на 30 минут
        )
        logger.info(f"Job added: daily_collection with schedule '{daily_stats_cron}'")

        # 2. Недельная агрегация - читаем расписание из БД
        weekly_stats_cron = settings_mgr.get('schedule.weekly_stats', default='0 4 * * 1')  # по умолчанию понедельник 04:00
        logger.info(f"Weekly stats schedule from settings: {weekly_stats_cron}")

        self.scheduler.add_job(
            func=self._weekly_aggregation_job,
            trigger=CronTrigger.from_crontab(weekly_stats_cron),
            id='weekly_aggregation',
            name='Weekly Statistics Aggregation',
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=7200  # может опоздать на 2 часа
        )
        logger.info(f"Job added: weekly_aggregation with schedule '{weekly_stats_cron}'")

        # 3. Поиск проблем каждые 6 часов
        self.scheduler.add_job(
            func=self._find_problems_job,
            trigger=CronTrigger(hour='*/6'),  # каждые 6 часов
            id='find_problems',
            name='Find Problematic Campaigns',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Job added: find_problems every 6 hours")

        # 4. Пересчет stat_periods каждый час
        self.scheduler.add_job(
            func=self._recalculate_periods_job,
            trigger=CronTrigger(minute=0),  # каждый час в начале
            id='recalculate_periods',
            name='Recalculate Stat Periods',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Job added: recalculate_periods every hour")

        # 5. Очистка старых данных раз в неделю по воскресеньям в 5:00 UTC
        self.scheduler.add_job(
            func=self._cleanup_old_data_job,
            trigger=CronTrigger(day_of_week='sun', hour=5, minute=0),
            id='cleanup_old_data',
            name='Cleanup Old Data',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Job added: cleanup_old_data on Sundays at 05:00 UTC")

        logger.info(f"Total jobs configured: {len(self.scheduler.get_jobs())}")

    def start(self):
        """Запускает планировщик"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("[OK] Scheduler started")
        else:
            logger.warning("Scheduler already running")

    def stop(self):
        """Останавливает планировщик"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("[OK] Scheduler stopped")
        else:
            logger.warning("Scheduler not running")

    def is_running(self) -> bool:
        """Проверяет запущен ли планировщик"""
        return self.scheduler.running

    def get_jobs(self) -> list:
        """Получает список задач"""
        return self.scheduler.get_jobs()

    def run_job_now(self, job_id: str) -> bool:
        """
        Запускает задачу немедленно

        Args:
            job_id: ID задачи

        Returns:
            True если успешно
        """
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.modify(next_run_time=get_now())
                logger.info(f"Job {job_id} scheduled to run now")
                return True
            else:
                logger.error(f"Job {job_id} not found")
                return False
        except Exception as e:
            logger.error(f"Error running job {job_id}: {e}")
            return False

    def _daily_collection_job(self):
        """Ежедневный сбор данных"""
        logger.info("=" * 60)
        logger.info("SCHEDULED JOB: Daily Collection")
        logger.info("=" * 60)

        try:
            stats = self.collector.daily_collect()

            logger.info(f"Daily collection completed: {stats['campaigns_processed']} campaigns processed")

            # Можно отправить уведомление если нужно
            if stats['errors'] > 0:
                logger.warning(f"Daily collection had {stats['errors']} errors")

        except Exception as e:
            logger.error(f"Daily collection job failed: {e}")
            raise

    def _weekly_aggregation_job(self):
        """Недельная агрегация"""
        logger.info("=" * 60)
        logger.info("SCHEDULED JOB: Weekly Aggregation")
        logger.info("=" * 60)

        try:
            count = aggregate_weekly_stats()
            logger.info(f"Weekly aggregation completed: {count} campaigns aggregated")

        except Exception as e:
            logger.error(f"Weekly aggregation job failed: {e}")
            raise

    def _find_problems_job(self):
        """Поиск проблемных кампаний"""
        logger.info("=" * 60)
        logger.info("SCHEDULED JOB: Find Problems")
        logger.info("=" * 60)

        try:
            # TODO: реализовать в этапе 17 (система алертов)
            logger.info("Problem detection not yet implemented")

        except Exception as e:
            logger.error(f"Find problems job failed: {e}")
            raise

    def _recalculate_periods_job(self):
        """Пересчет stat_periods из дневных данных"""
        logger.info("=" * 60)
        logger.info("SCHEDULED JOB: Recalculate Stat Periods")
        logger.info("=" * 60)

        try:
            # Пересчитываем все периоды (7days, 14days, 30days)
            result = recalculate_stat_periods()

            logger.info(f"Recalculation completed:")
            logger.info(f"  - Periods processed:   {result['periods_processed']}")
            logger.info(f"  - Campaigns processed: {result['campaigns_processed']}")
            logger.info(f"  - Records created:     {result['records_created']}")
            logger.info(f"  - Records updated:     {result['records_updated']}")
            logger.info(f"  - Records deleted:     {result['records_deleted']}")

            if result['errors']:
                logger.warning(f"Recalculation had {len(result['errors'])} errors")

        except Exception as e:
            logger.error(f"Recalculate periods job failed: {e}")
            raise

    def _cleanup_old_data_job(self):
        """Очистка старых данных"""
        logger.info("=" * 60)
        logger.info("SCHEDULED JOB: Cleanup Old Data")
        logger.info("=" * 60)

        try:
            # Читаем период хранения данных из настроек
            from services.settings_manager import get_settings_manager
            settings_mgr = get_settings_manager()
            retention_days = int(settings_mgr.get('data.retention_days', default=90))

            logger.info(f"Retention period: {retention_days} days")

            # Очищаем данные старше указанного количества дней
            result = cleanup_old_data(days_to_keep=retention_days)

            logger.info(f"Cleanup completed:")
            logger.info(f"  - Campaign stats: {result['deleted']['campaign_stats']:,}")
            logger.info(f"  - TS stats: {result['deleted']['ts_stats']:,}")
            logger.info(f"  - Offer stats: {result['deleted']['offer_stats']:,}")
            logger.info(f"  - Network stats: {result['deleted']['network_stats']:,}")
            logger.info(f"  - TOTAL: {result['deleted']['total']:,}")

            if result['errors']:
                logger.warning(f"Cleanup had {len(result['errors'])} errors")

        except Exception as e:
            logger.error(f"Cleanup job failed: {e}")
            raise

    def _job_executed(self, event):
        """Обработчик успешного выполнения"""
        logger.info(f"Job {event.job_id} executed successfully")

    def _job_error(self, event):
        """Обработчик ошибок"""
        logger.error(f"Job {event.job_id} failed with exception: {event.exception}")

    def get_next_run_times(self) -> Dict[str, Any]:
        """Получает время следующего запуска для всех задач"""
        jobs_info = {}

        for job in self.scheduler.get_jobs():
            jobs_info[job.id] = {
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger)
            }

        return jobs_info
