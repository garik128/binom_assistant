"""
Планировщик автозапуска модулей

Использует APScheduler для запуска модулей по расписанию.
Читает конфигурацию из БД и создает задачи для enabled модулей.
"""
import logging
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from storage.database.base import get_session
from storage.database.models import ModuleConfig as ModuleConfigDB
from .module_runner import ModuleRunner
from .base_module import ModuleConfig
from config import get_config

logger = logging.getLogger(__name__)


class ModuleScheduler:
    """
    Планировщик автозапуска модулей

    Использование:
        scheduler = ModuleScheduler()
        scheduler.setup_module_jobs()
        scheduler.start()
        # ... работа приложения ...
        scheduler.stop()

    Примечания по производительности:
        - Максимум 5 модулей выполняются параллельно (max_workers=5)
        - Если запускается больше модулей одновременно, они встают в очередь
        - Пример: 42 модуля в 9:00 выполнятся за ~4 минуты (при ~30 сек на модуль)
        - Рекомендация: Разносите время запуска модулей (9:00, 9:15, 10:00 и т.д.)
          чтобы избежать очередей и получать результаты быстрее
        - SQLite блокировки обрабатываются автоматически через retry с задержкой
    """

    def __init__(self):
        """Инициализация планировщика"""
        config = get_config()
        timezone_str = config.timezone

        # ВАЖНО: Ограничиваем количество параллельных воркеров
        # Если запустится много модулей одновременно (например, все в 9:00),
        # они будут выполняться порциями по max_workers, остальные в очереди
        # Это предотвращает перегрузку БД (SQLite) и системы
        from apscheduler.executors.pool import ThreadPoolExecutor
        executors = {
            'default': ThreadPoolExecutor(max_workers=5)  # Максимум 5 модулей параллельно
        }

        self.scheduler = BackgroundScheduler(
            timezone=timezone_str,
            executors=executors
        )
        self.runner = ModuleRunner()

        # Добавляем обработчики событий
        self.scheduler.add_listener(
            self._job_executed,
            EVENT_JOB_EXECUTED
        )
        self.scheduler.add_listener(
            self._job_error,
            EVENT_JOB_ERROR
        )

        logger.info(f"ModuleScheduler initialized with timezone: {timezone_str}, max_workers: 5")

    def setup_module_jobs(self):
        """
        Настраивает задачи для всех модулей с расписанием.

        Читает конфигурации из БД и создает задачи для enabled модулей.
        """
        logger.info("=" * 60)
        logger.info("Setting up module scheduled jobs...")
        logger.info("=" * 60)

        job_count = 0
        skipped_count = 0

        try:
            # Используем get_session() как generator
            session_generator = get_session()
            session = next(session_generator)
            try:
                # Получаем все модули с расписанием
                configs = session.query(ModuleConfigDB).filter(
                    ModuleConfigDB.enabled == True,
                    ModuleConfigDB.schedule.isnot(None)
                ).all()

                logger.info(f"Found {len(configs)} modules with schedule in DB")

                for config in configs:
                    logger.info(f"\nProcessing module: {config.module_id}")
                    logger.info(f"  Schedule: '{config.schedule}'")
                    logger.info(f"  Enabled: {config.enabled}")

                    if config.schedule and config.schedule.strip():
                        success = self._add_module_job(
                            module_id=config.module_id,
                            schedule=config.schedule,
                            params=config.params or {}
                        )
                        if success:
                            job_count += 1
                            logger.info(f"  [OK] Job added successfully")
                        else:
                            skipped_count += 1
                            logger.warning(f"  [SKIP] Failed to add job")
                    else:
                        skipped_count += 1
                        logger.warning(f"  [SKIP] Empty schedule")

            finally:
                try:
                    next(session_generator)
                except StopIteration:
                    pass

        except Exception as e:
            logger.error(f"Error setting up module jobs: {e}", exc_info=True)

        logger.info("=" * 60)
        logger.info(f"Module scheduler: {job_count} jobs configured, {skipped_count} skipped")
        logger.info("=" * 60)

        # Показываем список задач
        self._log_jobs()

    def _add_module_job(
        self,
        module_id: str,
        schedule: str,
        params: Dict[str, Any]
    ) -> bool:
        """
        Добавляет задачу для модуля.

        Args:
            module_id: ID модуля
            schedule: Cron expression
            params: Параметры запуска модуля

        Returns:
            True если успешно
        """
        try:
            # Получаем timezone из конфига
            config = get_config()
            timezone_str = config.timezone

            # Создаем trigger из cron expression
            trigger = CronTrigger.from_crontab(schedule, timezone=timezone_str)

            # Добавляем задачу
            self.scheduler.add_job(
                func=self._run_module_job,
                trigger=trigger,
                args=[module_id, params],
                id=f'module_{module_id}',
                name=f'Module: {module_id}',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300  # может опоздать на 5 минут
            )

            logger.info(f"Job added for module '{module_id}' with schedule: {schedule}")
            return True

        except Exception as e:
            logger.error(f"Failed to add job for module '{module_id}': {e}")
            return False

    def update_module_job(
        self,
        module_id: str,
        enabled: bool,
        schedule: Optional[str],
        params: Optional[Dict[str, Any]] = None
    ):
        """
        Обновляет задачу модуля при изменении конфигурации.

        Args:
            module_id: ID модуля
            enabled: Модуль включен
            schedule: Новое расписание (cron)
            params: Параметры запуска
        """
        job_id = f'module_{module_id}'

        # Удаляем существующую задачу
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed old job for module '{module_id}'")
        except Exception:
            pass  # Задачи могло не быть

        # Добавляем новую задачу если модуль enabled и есть расписание
        if enabled and schedule and schedule.strip():
            self._add_module_job(
                module_id=module_id,
                schedule=schedule,
                params=params or {}
            )

            # ВАЖНО: Если планировщик не запущен, запускаем его
            # Это может произойти если приложение стартовало с first_run=true
            # или произошла ошибка при инициализации
            if not self.scheduler.running:
                logger.warning(f"Scheduler was not running, starting it now...")
                self.start()
        else:
            logger.info(f"Module '{module_id}' auto-run disabled")

    def remove_module_job(self, module_id: str):
        """
        Удаляет задачу модуля.

        Args:
            module_id: ID модуля
        """
        job_id = f'module_{module_id}'

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job for module '{module_id}'")
        except Exception as e:
            logger.warning(f"Could not remove job for module '{module_id}': {e}")

    def start(self):
        """Запускает планировщик"""
        try:
            if not self.scheduler.running:
                logger.info("Starting module scheduler...")
                self.scheduler.start()
                logger.info("[OK] Module scheduler started successfully")

                # Логируем задачи после запуска
                jobs = self.get_jobs()
                logger.info(f"Active jobs after start: {len(jobs)}")
                for job in jobs:
                    logger.info(f"  - {job['name']}: next_run={job['next_run_time']}")
            else:
                logger.warning("Module scheduler already running")
        except Exception as e:
            logger.error(f"FAILED to start module scheduler: {e}", exc_info=True)

    def stop(self):
        """Останавливает планировщик"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("[OK] Module scheduler stopped")
        else:
            logger.warning("Module scheduler not running")

    def is_running(self) -> bool:
        """Проверяет запущен ли планировщик"""
        return self.scheduler.running

    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        Получает список всех задач.

        Returns:
            Список задач с информацией
        """
        jobs = []

        for job in self.scheduler.get_jobs():
            try:
                next_run = getattr(job, 'next_run_time', None)
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': next_run,
                    'trigger': str(job.trigger)
                })
            except Exception as e:
                logger.warning(f"Could not get info for job {job.id}: {e}")

        return jobs

    def _run_module_job(self, module_id: str, params: Dict[str, Any]):
        """
        Выполняет запуск модуля.

        ВАЖНО: Ловит ВСЕ исключения и не пробрасывает их в APScheduler,
        чтобы scheduled задачи продолжали работать даже после ошибок.

        Args:
            module_id: ID модуля
            params: Параметры запуска
        """
        logger.info("=" * 60)
        logger.info(f"SCHEDULED RUN: Module '{module_id}'")
        logger.info("=" * 60)

        try:
            # ВАЖНО: не создаем config здесь, передаем None
            # ModuleRunner.run_module() сам загрузит полную конфигурацию из БД
            # включая alerts_enabled, schedule и остальные поля
            # params используются только для передачи в БД при сохранении run

            # Запускаем модуль
            result = self.runner.run_module(
                module_id=module_id,
                config=None,  # Загрузится из БД с полными настройками
                use_cache=False  # Для автозапуска не используем кэш
            )

            if result.status == 'success':
                logger.info(f"Module '{module_id}' completed successfully")

                # Логируем сводку если есть
                if result.data and 'summary' in result.data:
                    summary = result.data['summary']
                    logger.info(f"Summary: {summary}")
            else:
                logger.error(f"Module '{module_id}' failed: {result.error}")

        except Exception as e:
            # КРИТИЧНО: НЕ пробрасываем исключение в APScheduler!
            # Иначе scheduled задачи могут перестать работать
            logger.error(
                f"CRITICAL: Exception in scheduled module '{module_id}': {e}",
                exc_info=True
            )
            # TODO: в будущем здесь можно добавить:
            # - сохранение ошибки в БД для отображения в UI
            # - отправку критического алерта админу
            # - логику повторных попыток с экспоненциальной задержкой

    def _job_executed(self, event):
        """Обработчик успешного выполнения"""
        logger.info(f"Job {event.job_id} executed successfully")

    def _job_error(self, event):
        """Обработчик ошибок"""
        logger.error(
            f"Job {event.job_id} failed with exception: {event.exception}",
            exc_info=event.exception
        )

    def _log_jobs(self):
        """Логирует список всех задач"""
        jobs = self.get_jobs()

        if not jobs:
            logger.info("No scheduled module jobs")
            return

        logger.info(f"Scheduled module jobs ({len(jobs)}):")
        for job in jobs:
            logger.info(f"  - {job['name']} | Next run: {job['next_run_time']} | {job['trigger']}")


# Глобальный экземпляр планировщика
_scheduler_instance: Optional[ModuleScheduler] = None


def get_module_scheduler() -> ModuleScheduler:
    """
    Получает глобальный экземпляр планировщика модулей.

    Returns:
        Экземпляр ModuleScheduler
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = ModuleScheduler()

    return _scheduler_instance
