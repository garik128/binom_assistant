"""
Сборщик данных из Binom API - версия 2

Расширенная версия с поддержкой:
- Traffic Sources
- Offers
- Affiliate Networks

АРХИТЕКТУРА БЛОКОВ:
Вместо одного большого запроса, делаем 4 блока с паузами:
1. Campaigns Block (кампании)
2. Traffic Sources Block (источники трафика)
3. Offers Block (офферы)
4. Affiliate Networks Block (партнерки)

ВАЖНО: Имена могут меняться в Binom!
- current_name в Campaign обновляется при каждом запуске
- name в TrafficSource обновляется при каждом запуске
- name в Offer обновляется при каждом запуске
- name в AffiliateNetwork обновляется при каждом запуске

ПАУЗЫ между блоками: настраиваются через COLLECTOR_API_PAUSE (по умолчанию 3 секунды)
"""
import logging
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.exc import IntegrityError

from utils import get_now

from core.api_client import (
    BinomClient,
    CPLDetector,
    clean_campaigns_list,
    clean_traffic_sources_list,
    clean_offers_list,
    clean_affiliate_networks_list,
    normalize_campaign_data,
    normalize_traffic_source_data,
    normalize_offer_data,
    normalize_affiliate_network_data
)
from storage.database import (
    session_scope,
    Campaign,
    CampaignStatsDaily,
    StatPeriod,
    NameChange,
    TrafficSource,
    TrafficSourceStatsDaily,
    Offer,
    OfferStatsDaily,
    AffiliateNetwork,
    NetworkStatsDaily,
    BackgroundTask
)


logger = logging.getLogger(__name__)


class DataCollector:
    """
    Сборщик данных из Binom с расширенной поддержкой

    Поддерживает:
    - Campaigns (кампании)
    - Traffic Sources (источники трафика)
    - Offers (офферы)
    - Affiliate Networks (партнерские сети)

    Использование:
        collector = DataCollector()
        collector.daily_collect()
    """

    def __init__(self, skip_pauses: bool = False):
        """
        Инициализация сборщика

        Args:
            skip_pauses: Если True, пропускает все паузы (для первичной загрузки)
        """
        self.client = BinomClient()
        self.cpl_detector = CPLDetector()

        # Загружаем менеджер настроек
        try:
            from services.settings_manager import get_settings_manager
            self.settings = get_settings_manager()
            logger.debug("SettingsManager loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load SettingsManager: {e}. Using defaults.")
            self.settings = None

        # Настройки пауз (в секундах)
        self.skip_pauses = skip_pauses
        if skip_pauses:
            self.pause_between_blocks = 0
            logger.warning("FAST MODE: All pauses disabled!")
        else:
            # Загружаем паузу из настроек (settings -> .env -> default 3.0)
            if self.settings:
                self.pause_between_blocks = float(self.settings.get('collector.api_pause', default=3.0))
            else:
                self.pause_between_blocks = 3.0  # дефолт если нет settings
            logger.info(f"API pause between requests: {self.pause_between_blocks}s")

        logger.info(f"DataCollector initialized (skip_pauses={skip_pauses})")

    def _update_task_progress(self, task_id: Optional[int], progress: int, message: str):
        """
        Обновляет прогресс задачи в БД

        Args:
            task_id: ID задачи (None если задача не отслеживается)
            progress: прогресс 0-100
            message: текущее действие
        """
        if task_id is None:
            return

        try:
            with session_scope() as session:
                task = session.query(BackgroundTask).filter_by(id=task_id).first()
                if task:
                    task.progress = progress
                    task.progress_message = message
                    if progress > 0 and task.status == 'pending':
                        task.status = 'running'
                        task.started_at = get_now()
                    session.commit()
        except Exception as e:
            logger.error(f"Failed to update task progress: {e}")

    def _generate_date_range(self, days: int) -> List[date]:
        """
        Генерирует список дат за последние N дней (включая сегодня)

        Args:
            days: количество дней назад

        Returns:
            Список объектов date в порядке от старой к новой
        """
        today = date.today()
        dates = []
        for i in range(days - 1, -1, -1):
            dates.append(today - timedelta(days=i))
        return dates

    def daily_collect(self, task_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Ежедневный сбор данных со всех источников

        СТРАТЕГИЯ БЛОКОВ:
        1. Campaigns Block - собирает кампании за настраиваемый период (по умолчанию 7 дней)
        2. Пауза 2 минуты
        3. Traffic Sources Block - собирает источники трафика
        4. Пауза 2 минуты
        5. Offers Block - собирает офферы
        6. Пауза 2 минуты
        7. Affiliate Networks Block - собирает партнерки

        Период обновления берётся из настроек:
        - БД (app_settings.collector.update_days)
        - .env (COLLECTOR_UPDATE_DAYS)
        - Hardcoded default (7)

        Args:
            task_id: ID задачи для отслеживания прогресса (опционально)

        Returns:
            Словарь со статистикой сбора
        """
        logger.info("=" * 80)
        logger.info("Starting daily data collection (V2 - Extended)")
        logger.info("=" * 80)

        # Читаем период обновления из настроек
        update_days = 7  # дефолт
        if self.settings:
            update_days = self.settings.get('collector.update_days', default=7)
            logger.info(f"Update period from settings: {update_days} days")
        else:
            logger.info(f"Using default update period: {update_days} days")

        start_time = get_now()

        # Начальный прогресс
        self._update_task_progress(task_id, 0, "Начало сбора данных")

        # Статистика
        stats = {
            # Campaigns
            'campaigns_processed': 0,
            'campaigns_new': 0,
            'campaigns_updated': 0,
            'campaigns_name_changes': 0,
            'campaigns_cpl_detected': 0,

            # Traffic Sources
            'ts_processed': 0,
            'ts_new': 0,
            'ts_updated': 0,
            'ts_name_changes': 0,

            # Offers
            'offers_processed': 0,
            'offers_new': 0,
            'offers_updated': 0,
            'offers_name_changes': 0,

            # Networks
            'networks_processed': 0,
            'networks_new': 0,
            'networks_updated': 0,
            'networks_name_changes': 0,

            # Общее
            'errors': 0,
            'start_time': start_time,
            'end_time': None,
            'duration_seconds': 0
        }

        try:
            # ==========================================
            # БЛОК 1: CAMPAIGNS
            # ==========================================
            logger.info("\n" + "=" * 80)
            logger.info("BLOCK 1: CAMPAIGNS")
            logger.info("=" * 80)

            campaigns_stats = self._collect_campaigns_block(period_days=update_days)

            # Обновляем общую статистику
            stats['campaigns_processed'] = campaigns_stats['processed']
            stats['campaigns_new'] = campaigns_stats['new']
            stats['campaigns_updated'] = campaigns_stats['updated']
            stats['campaigns_name_changes'] = campaigns_stats['name_changes']
            stats['campaigns_cpl_detected'] = campaigns_stats['cpl_detected']
            stats['errors'] += campaigns_stats['errors']

            logger.info(f"Campaigns block completed: {campaigns_stats['processed']} processed")
            self._update_task_progress(task_id, 15, f"Блок 1 завершен: {campaigns_stats['processed']} кампаний")

            # Пауза перед следующим блоком
            logger.info(f"\nPausing {self.pause_between_blocks} seconds before next block...")
            time.sleep(self.pause_between_blocks)

            # ==========================================
            # БЛОК 2: TRAFFIC SOURCES
            # ==========================================
            logger.info("\n" + "=" * 80)
            logger.info("BLOCK 2: TRAFFIC SOURCES")
            logger.info("=" * 80)

            ts_stats = self._collect_traffic_sources_block()

            stats['ts_processed'] = ts_stats['processed']
            stats['ts_new'] = ts_stats['new']
            stats['ts_updated'] = ts_stats['updated']
            stats['ts_name_changes'] = ts_stats['name_changes']
            stats['errors'] += ts_stats['errors']

            logger.info(f"Traffic sources block completed: {ts_stats['processed']} processed")
            self._update_task_progress(task_id, 30, f"Блок 2 завершен: {ts_stats['processed']} источников")

            # Пауза
            logger.info(f"\nPausing {self.pause_between_blocks} seconds before next block...")
            time.sleep(self.pause_between_blocks)

            # ==========================================
            # БЛОК 3: OFFERS
            # ==========================================
            logger.info("\n" + "=" * 80)
            logger.info("BLOCK 3: OFFERS")
            logger.info("=" * 80)

            offers_stats = self._collect_offers_block()

            stats['offers_processed'] = offers_stats['processed']
            stats['offers_new'] = offers_stats['new']
            stats['offers_updated'] = offers_stats['updated']
            stats['offers_name_changes'] = offers_stats['name_changes']
            stats['errors'] += offers_stats['errors']

            logger.info(f"Offers block completed: {offers_stats['processed']} processed")
            self._update_task_progress(task_id, 45, f"Блок 3 завершен: {offers_stats['processed']} офферов")

            # Пауза
            logger.info(f"\nPausing {self.pause_between_blocks} seconds before next block...")
            time.sleep(self.pause_between_blocks)

            # ==========================================
            # БЛОК 4: AFFILIATE NETWORKS
            # ==========================================
            logger.info("\n" + "=" * 80)
            logger.info("BLOCK 4: AFFILIATE NETWORKS")
            logger.info("=" * 80)

            networks_stats = self._collect_networks_block()

            stats['networks_processed'] = networks_stats['processed']
            stats['networks_new'] = networks_stats['new']
            stats['networks_updated'] = networks_stats['updated']
            stats['networks_name_changes'] = networks_stats['name_changes']
            stats['errors'] += networks_stats['errors']

            logger.info(f"Affiliate networks block completed: {networks_stats['processed']} processed")
            self._update_task_progress(task_id, 60, f"Блок 4 завершен: {networks_stats['processed']} партнерок")

            # ==========================================
            # БЛОК 5: ДНЕВНАЯ СТАТИСТИКА
            # ==========================================
            logger.info("\n" + "=" * 80)
            logger.info(f"BLOCK 5: DAILY STATS FOR LAST {update_days} DAYS")
            logger.info("=" * 80)
            self._update_task_progress(task_id, 65, f"Блок 5: сбор дневной статистики за {update_days} дней")

            dates = self._generate_date_range(update_days)
            logger.info(f"Collecting daily stats for {len(dates)} days: {dates[0]} to {dates[-1]}")

            # ВАЖНО: Получаем список всех campaign IDs за период
            # Это позволит создавать записи с нулями для дней без трафика
            logger.info(f"\nGetting all campaign IDs for {update_days}-day period...")
            campaign_ids = self._get_all_campaign_ids_for_period(update_days)
            logger.info(f"Will track {len(campaign_ids)} campaigns (creating zeros for days without traffic)")

            daily_stats_summary = {
                'campaigns': {'created': 0, 'updated': 0, 'skipped': 0, 'zero_records': 0},
                'traffic_sources': {'created': 0, 'updated': 0, 'skipped': 0},
                'offers': {'created': 0, 'updated': 0, 'skipped': 0},
                'networks': {'created': 0, 'updated': 0, 'skipped': 0}
            }

            for day_num, target_date in enumerate(dates, 1):
                logger.info(f"\n--- Day {day_num}/{len(dates)}: {target_date} ---")

                # Campaigns daily stats (с нулями для дней без трафика)
                logger.info(f"Pausing {self.pause_between_blocks} seconds...")
                time.sleep(self.pause_between_blocks)
                camp_stats = self._collect_campaign_daily_stats(target_date, campaign_ids=campaign_ids)
                for k, v in camp_stats.items():
                    daily_stats_summary['campaigns'][k] += v

                # Traffic Sources daily stats
                logger.info(f"Pausing {self.pause_between_blocks} seconds...")
                time.sleep(self.pause_between_blocks)
                ts_stats = self._collect_ts_daily_stats(target_date)
                for k, v in ts_stats.items():
                    daily_stats_summary['traffic_sources'][k] += v

                # Offers daily stats
                logger.info(f"Pausing {self.pause_between_blocks} seconds...")
                time.sleep(self.pause_between_blocks)
                offer_stats = self._collect_offer_daily_stats(target_date)
                for k, v in offer_stats.items():
                    daily_stats_summary['offers'][k] += v

                # Networks daily stats
                logger.info(f"Pausing {self.pause_between_blocks} seconds...")
                time.sleep(self.pause_between_blocks)
                net_stats = self._collect_network_daily_stats(target_date)
                for k, v in net_stats.items():
                    daily_stats_summary['networks'][k] += v

            # Добавляем статистику дневных данных в общую
            stats['daily_stats'] = daily_stats_summary

            logger.info("\nDaily stats collection completed")
            logger.info(f"Campaigns: {daily_stats_summary['campaigns']}")
            logger.info(f"Traffic Sources: {daily_stats_summary['traffic_sources']}")
            logger.info(f"Offers: {daily_stats_summary['offers']}")
            logger.info(f"Networks: {daily_stats_summary['networks']}")
            self._update_task_progress(task_id, 95, "Блок 5 завершен: дневная статистика собрана")

            # Финализация
            end_time = get_now()
            duration = (end_time - start_time).total_seconds()

            stats['end_time'] = end_time
            stats['duration_seconds'] = duration

            # Итоговый отчет
            logger.info("\n" + "=" * 80)
            logger.info("DAILY COLLECTION COMPLETED (V2)")
            logger.info("=" * 80)
            logger.info(f"Total duration: {duration:.2f} seconds ({duration/60:.1f} minutes)")
            logger.info("")
            logger.info("CAMPAIGNS:")
            logger.info(f"  Processed: {stats['campaigns_processed']}")
            logger.info(f"  New: {stats['campaigns_new']}")
            logger.info(f"  Updated: {stats['campaigns_updated']}")
            logger.info(f"  Name changes: {stats['campaigns_name_changes']}")
            logger.info(f"  CPL detected: {stats['campaigns_cpl_detected']}")
            logger.info("")
            logger.info("TRAFFIC SOURCES:")
            logger.info(f"  Processed: {stats['ts_processed']}")
            logger.info(f"  New: {stats['ts_new']}")
            logger.info(f"  Updated: {stats['ts_updated']}")
            logger.info(f"  Name changes: {stats['ts_name_changes']}")
            logger.info("")
            logger.info("OFFERS:")
            logger.info(f"  Processed: {stats['offers_processed']}")
            logger.info(f"  New: {stats['offers_new']}")
            logger.info(f"  Updated: {stats['offers_updated']}")
            logger.info(f"  Name changes: {stats['offers_name_changes']}")
            logger.info("")
            logger.info("AFFILIATE NETWORKS:")
            logger.info(f"  Processed: {stats['networks_processed']}")
            logger.info(f"  New: {stats['networks_new']}")
            logger.info(f"  Updated: {stats['networks_updated']}")
            logger.info(f"  Name changes: {stats['networks_name_changes']}")
            logger.info("")
            logger.info(f"Total errors: {stats['errors']}")
            logger.info("=" * 80)

            # Финальный прогресс
            self._update_task_progress(task_id, 100, "Сбор данных завершен успешно")

            # Сохраняем результат в задачу
            if task_id:
                try:
                    with session_scope() as session:
                        task = session.query(BackgroundTask).filter_by(id=task_id).first()
                        if task:
                            task.status = 'completed'
                            task.completed_at = get_now()
                            task.result = {
                                'campaigns': stats['campaigns_processed'],
                                'traffic_sources': stats['ts_processed'],
                                'offers': stats['offers_processed'],
                                'networks': stats['networks_processed'],
                                'errors': stats['errors']
                            }
                            session.commit()
                except Exception as ex:
                    logger.error(f"Failed to save task result: {ex}")

            return stats

        except Exception as e:
            logger.error(f"Fatal error in daily_collect: {e}")
            import traceback
            traceback.print_exc()
            stats['errors'] += 1

            # Отмечаем задачу как failed
            if task_id:
                try:
                    with session_scope() as session:
                        task = session.query(BackgroundTask).filter_by(id=task_id).first()
                        if task:
                            task.status = 'failed'
                            task.completed_at = get_now()
                            task.error = str(e)
                            session.commit()
                except Exception as ex:
                    logger.error(f"Failed to save task error: {ex}")

            return stats

    def _collect_campaigns_block(self, period_days: int = 7) -> Dict[str, int]:
        """
        Блок сбора кампаний за указанный период

        Args:
            period_days: количество дней для сбора (по умолчанию 7)

        Returns:
            Статистика: processed, new, updated, name_changes, cpl_detected, errors
        """
        stats = {
            'processed': 0,
            'new': 0,
            'updated': 0,
            'name_changes': 0,
            'cpl_detected': 0,
            'errors': 0
        }

        try:
            # Получаем кампании за указанный период
            if period_days <= 7:
                logger.info(f"Fetching campaigns for last {period_days} days (using date=3)...")
                raw_campaigns = self.client.get_campaigns(
                    date="3",  # последние 7 дней
                    status=2,  # с трафиком
                    val_page="all"
                )
            else:
                # Для периодов > 7 дней используем произвольный период
                today = date.today()
                start_date = today - timedelta(days=period_days - 1)
                logger.info(f"Fetching campaigns for {period_days} days ({start_date} to {today})...")
                raw_campaigns = self.client.get_campaigns_custom_period(
                    date_start=start_date.isoformat(),
                    date_end=today.isoformat(),
                    status=2,
                    val_page="all"
                )

            if not raw_campaigns:
                logger.warning("No campaigns received")
                return stats

            logger.info(f"Received {len(raw_campaigns)} campaigns")

            # Очищаем данные
            cleaned_campaigns = clean_campaigns_list(raw_campaigns)

            # Обрабатываем каждую кампанию
            for campaign_data in cleaned_campaigns:
                try:
                    # Нормализуем типы
                    campaign_data = normalize_campaign_data(campaign_data)

                    # Сохраняем только кампании с трафиком (клики > 0)
                    clicks = campaign_data.get('clicks', 0)

                    if clicks == 0:
                        logger.debug(f"Skipping campaign {campaign_data['id']} - no traffic (clicks=0)")
                        continue

                    # Сохраняем/обновляем кампанию
                    result = self._save_or_update_campaign(campaign_data)

                    if result['is_new']:
                        stats['new'] += 1
                    else:
                        stats['updated'] += 1

                    if result['name_changed']:
                        stats['name_changes'] += 1

                    if result['is_cpl']:
                        stats['cpl_detected'] += 1

                    stats['processed'] += 1

                except Exception as e:
                    logger.error(f"Error processing campaign {campaign_data.get('id')}: {e}")
                    stats['errors'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error in _collect_campaigns_block: {e}")
            stats['errors'] += 1
            return stats

    def _collect_traffic_sources_block(self, period_days: int = 7) -> Dict[str, int]:
        """
        Блок сбора источников трафика за указанный период

        Args:
            period_days: количество дней для сбора (по умолчанию 7)

        Returns:
            Статистика: processed, new, updated, name_changes, errors
        """
        stats = {
            'processed': 0,
            'new': 0,
            'updated': 0,
            'name_changes': 0,
            'errors': 0
        }

        try:
            if period_days <= 7:
                logger.info(f"Fetching traffic sources for last {period_days} days (using date=3)...")
                raw_ts = self.client.get_traffic_sources(
                    date="3",
                    status=2,
                    val_page="all"
                )
            else:
                today = date.today()
                start_date = today - timedelta(days=period_days - 1)
                logger.info(f"Fetching traffic sources for {period_days} days ({start_date} to {today})...")
                raw_ts = self.client.get_traffic_sources(
                    date="12",
                    status=2,
                    val_page="all",
                    date_start=start_date.isoformat(),
                    date_end=today.isoformat()
                )

            if not raw_ts:
                logger.warning("No traffic sources received")
                return stats

            logger.info(f"Received {len(raw_ts)} traffic sources")

            # Очищаем и нормализуем
            cleaned_ts = clean_traffic_sources_list(raw_ts)

            for ts_data in cleaned_ts:
                try:
                    ts_data = normalize_traffic_source_data(ts_data)

                    # Сохраняем/обновляем
                    result = self._save_or_update_traffic_source(ts_data)

                    if result['is_new']:
                        stats['new'] += 1
                    else:
                        stats['updated'] += 1

                    if result['name_changed']:
                        stats['name_changes'] += 1

                    stats['processed'] += 1

                except Exception as e:
                    logger.error(f"Error processing traffic source {ts_data.get('id')}: {e}")
                    stats['errors'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error in _collect_traffic_sources_block: {e}")
            stats['errors'] += 1
            return stats

    def _collect_offers_block(self, period_days: int = 7) -> Dict[str, int]:
        """
        Блок сбора офферов за указанный период

        Args:
            period_days: количество дней для сбора (по умолчанию 7)

        Returns:
            Статистика: processed, new, updated, name_changes, errors
        """
        stats = {
            'processed': 0,
            'new': 0,
            'updated': 0,
            'name_changes': 0,
            'errors': 0
        }

        try:
            if period_days <= 7:
                logger.info(f"Fetching offers for last {period_days} days (using date=3)...")
                raw_offers = self.client.get_offers(
                    date="3",
                    status=2,
                    val_page="all"
                )
            else:
                today = date.today()
                start_date = today - timedelta(days=period_days - 1)
                logger.info(f"Fetching offers for {period_days} days ({start_date} to {today})...")
                raw_offers = self.client.get_offers(
                    date="12",
                    status=2,
                    val_page="all",
                    date_start=start_date.isoformat(),
                    date_end=today.isoformat()
                )

            if not raw_offers:
                logger.warning("No offers received")
                return stats

            logger.info(f"Received {len(raw_offers)} offers")

            # Очищаем и нормализуем
            cleaned_offers = clean_offers_list(raw_offers)

            for offer_data in cleaned_offers:
                try:
                    offer_data = normalize_offer_data(offer_data)

                    # Сохраняем/обновляем
                    result = self._save_or_update_offer(offer_data)

                    if result['is_new']:
                        stats['new'] += 1
                    else:
                        stats['updated'] += 1

                    if result['name_changed']:
                        stats['name_changes'] += 1

                    stats['processed'] += 1

                except Exception as e:
                    logger.error(f"Error processing offer {offer_data.get('id')}: {e}")
                    stats['errors'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error in _collect_offers_block: {e}")
            stats['errors'] += 1
            return stats

    def _collect_networks_block(self, period_days: int = 7) -> Dict[str, int]:
        """
        Блок сбора партнерских сетей за указанный период

        Args:
            period_days: количество дней для сбора (по умолчанию 7)

        Returns:
            Статистика: processed, new, updated, name_changes, errors
        """
        stats = {
            'processed': 0,
            'new': 0,
            'updated': 0,
            'name_changes': 0,
            'errors': 0
        }

        try:
            if period_days <= 7:
                logger.info(f"Fetching affiliate networks for last {period_days} days (using date=3)...")
                raw_networks = self.client.get_affiliate_networks(
                    date="3",
                    status=2,
                    val_page="all"
                )
            else:
                today = date.today()
                start_date = today - timedelta(days=period_days - 1)
                logger.info(f"Fetching affiliate networks for {period_days} days ({start_date} to {today})...")
                raw_networks = self.client.get_affiliate_networks(
                    date="12",
                    status=2,
                    val_page="all",
                    date_start=start_date.isoformat(),
                    date_end=today.isoformat()
                )

            if not raw_networks:
                logger.warning("No affiliate networks received")
                return stats

            logger.info(f"Received {len(raw_networks)} affiliate networks")

            # Очищаем и нормализуем
            cleaned_networks = clean_affiliate_networks_list(raw_networks)

            for network_data in cleaned_networks:
                try:
                    network_data = normalize_affiliate_network_data(network_data)

                    # Сохраняем/обновляем
                    result = self._save_or_update_network(network_data)

                    if result['is_new']:
                        stats['new'] += 1
                    else:
                        stats['updated'] += 1

                    if result['name_changed']:
                        stats['name_changes'] += 1

                    stats['processed'] += 1

                except Exception as e:
                    logger.error(f"Error processing network {network_data.get('id')}: {e}")
                    stats['errors'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error in _collect_networks_block: {e}")
            stats['errors'] += 1
            return stats

    def _save_or_update_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Сохраняет или обновляет кампанию в БД

        ВАЖНО: current_name ВСЕГДА обновляется при каждом запуске!

        Args:
            campaign_data: нормализованные данные кампании

        Returns:
            Dict: is_new, name_changed, is_cpl
        """
        binom_id = campaign_data['id']
        current_name = campaign_data['name']

        result = {
            'is_new': False,
            'name_changed': False,
            'is_cpl': False
        }

        with session_scope() as session:
            campaign = session.query(Campaign).filter_by(binom_id=binom_id).first()
            now = get_now()

            if not campaign:
                # Новая кампания
                logger.info(f"New campaign: {binom_id} - {current_name}")

                campaign = Campaign(
                    binom_id=binom_id,
                    current_name=current_name,
                    group_name=campaign_data.get('group_name', ''),
                    ts_name=campaign_data.get('ts_name', ''),
                    ts_id=None,  # будет заполнено позже при связывании
                    domain_name=campaign_data.get('domain_name', ''),
                    is_cpl_mode=False,
                    is_active=True,
                    status='active',
                    first_seen=now,
                    last_seen=now
                )

                session.add(campaign)
                session.flush()

                result['is_new'] = True

            else:
                # Обновляем существующую
                campaign.last_seen = now

                # ВАЖНО: Проверяем изменение имени
                if campaign.current_name != current_name:
                    logger.info(f"Name changed for {binom_id}: '{campaign.current_name}' -> '{current_name}'")

                    # Сохраняем изменение имени
                    name_change = NameChange(
                        campaign_id=campaign.internal_id,
                        old_name=campaign.current_name,
                        new_name=current_name,
                        changed_at=now
                    )
                    session.add(name_change)

                    # Обновляем текущее имя
                    campaign.current_name = current_name

                    result['name_changed'] = True

                # Обновляем остальные поля
                campaign.group_name = campaign_data.get('group_name', '')
                campaign.ts_name = campaign_data.get('ts_name', '')
                campaign.domain_name = campaign_data.get('domain_name', '')

            # Определяем тип (CPL/CPA)
            is_cpl = self.cpl_detector.detect(campaign_data)
            campaign.is_cpl_mode = is_cpl
            result['is_cpl'] = is_cpl

            session.commit()

        return result

    def _save_or_update_traffic_source(self, ts_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Сохраняет или обновляет источник трафика в БД

        ВАЖНО: name ВСЕГДА обновляется при каждом запуске!

        Args:
            ts_data: нормализованные данные источника

        Returns:
            Dict: is_new, name_changed
        """
        ts_id = ts_data['id']
        current_name = ts_data['name']

        result = {
            'is_new': False,
            'name_changed': False
        }

        with session_scope() as session:
            ts = session.query(TrafficSource).filter_by(id=ts_id).first()
            now = get_now()

            if not ts:
                # Новый источник
                logger.info(f"New traffic source: {ts_id} - {current_name}")

                ts = TrafficSource(
                    id=ts_id,
                    name=current_name,
                    status=ts_data.get('status', True),
                    first_seen=now,
                    last_seen=now
                )

                session.add(ts)
                result['is_new'] = True

            else:
                # Обновляем существующий
                ts.last_seen = now

                # ВАЖНО: Проверяем изменение имени
                if ts.name != current_name:
                    logger.info(f"TS name changed for {ts_id}: '{ts.name}' -> '{current_name}'")
                    ts.name = current_name
                    result['name_changed'] = True

                # Обновляем статус
                ts.status = ts_data.get('status', True)

            session.commit()

        return result

    def _save_or_update_offer(self, offer_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Сохраняет или обновляет оффер в БД

        ВАЖНО: name ВСЕГДА обновляется при каждом запуске!

        Args:
            offer_data: нормализованные данные оффера

        Returns:
            Dict: is_new, name_changed
        """
        offer_id = offer_data['id']
        current_name = offer_data['name']

        result = {
            'is_new': False,
            'name_changed': False
        }

        with session_scope() as session:
            offer = session.query(Offer).filter_by(id=offer_id).first()
            now = get_now()

            if not offer:
                # Новый оффер
                logger.info(f"New offer: {offer_id} - {current_name}")

                offer = Offer(
                    id=offer_id,
                    name=current_name,
                    network_id=offer_data.get('network_id'),
                    geo=offer_data.get('geo', ''),
                    payout=offer_data.get('payout'),
                    currency='usd',
                    status=offer_data.get('status', True),
                    is_banned=False,
                    first_seen=now,
                    last_seen=now
                )

                session.add(offer)
                result['is_new'] = True

            else:
                # Обновляем существующий
                offer.last_seen = now

                # ВАЖНО: Проверяем изменение имени
                if offer.name != current_name:
                    logger.info(f"Offer name changed for {offer_id}: '{offer.name}' -> '{current_name}'")
                    offer.name = current_name
                    result['name_changed'] = True

                # Обновляем остальные поля
                offer.network_id = offer_data.get('network_id')
                offer.geo = offer_data.get('geo', '')
                offer.payout = offer_data.get('payout')
                offer.status = offer_data.get('status', True)

            session.commit()

        return result

    def _save_or_update_network(self, network_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Сохраняет или обновляет партнерскую сеть в БД

        ВАЖНО: name ВСЕГДА обновляется при каждом запуске!

        Args:
            network_data: нормализованные данные сети

        Returns:
            Dict: is_new, name_changed
        """
        network_id = network_data['id']
        current_name = network_data['name']

        result = {
            'is_new': False,
            'name_changed': False
        }

        with session_scope() as session:
            network = session.query(AffiliateNetwork).filter_by(id=network_id).first()
            now = get_now()

            if not network:
                # Новая сеть
                logger.info(f"New affiliate network: {network_id} - {current_name}")

                network = AffiliateNetwork(
                    id=network_id,
                    name=current_name,
                    status=network_data.get('status', True),
                    first_seen=now,
                    last_seen=now
                )

                session.add(network)
                result['is_new'] = True

            else:
                # Обновляем существующую
                network.last_seen = now

                # ВАЖНО: Проверяем изменение имени
                if network.name != current_name:
                    logger.info(f"Network name changed for {network_id}: '{network.name}' -> '{current_name}'")
                    network.name = current_name
                    result['name_changed'] = True

                # Обновляем статус
                network.status = network_data.get('status', True)

            session.commit()

        return result

    # ========================================================================
    # МЕТОДЫ ДЛЯ СБОРА ДНЕВНОЙ СТАТИСТИКИ
    # ========================================================================

    def _get_all_campaign_ids_for_period(self, days: int) -> List[int]:
        """
        Получает список всех binom_id кампаний, которые работали хотя бы раз за период

        ВАЖНО: Используем status=2 чтобы получить только кампании с трафиком за период

        Args:
            days: количество дней для периода

        Returns:
            Список binom_id кампаний
        """
        today = date.today()
        start_date = today - timedelta(days=days - 1)

        logger.info(f"Getting all campaign IDs for period: {start_date} to {today}")

        # Запрашиваем все кампании за период с status=2 (с трафиком)
        raw_campaigns = self.client.get_campaigns(
            date="12",
            date_start=start_date.isoformat(),
            date_end=today.isoformat(),
            status=2,
            val_page="all"
        )

        if not raw_campaigns:
            logger.warning(f"No campaigns found for period {start_date} to {today}")
            return []

        cleaned = clean_campaigns_list(raw_campaigns)
        campaign_ids = [int(camp['id']) for camp in cleaned]

        logger.info(f"Found {len(campaign_ids)} campaigns with traffic in period")
        return campaign_ids

    def _collect_campaign_daily_stats(self, target_date: date, campaign_ids: Optional[List[int]] = None) -> Dict[str, int]:
        """
        Собирает дневную статистику по кампаниям за конкретный день

        НОВАЯ ЛОГИКА (исправление потери данных):
        1. Если передан campaign_ids - создаём записи для ВСЕХ кампаний из списка
        2. Запрашиваем данные за день с status=2 (только кампании с трафиком)
        3. Для кампаний с трафиком - сохраняем данные
        4. Для кампаний БЕЗ трафика (из списка) - создаём записи с НУЛЯМИ

        Args:
            target_date: дата для сбора
            campaign_ids: список binom_id кампаний (если None - старая логика)

        Returns:
            Статистика: created, updated, skipped, zero_records
        """
        logger.info(f"Collecting campaign daily stats for {target_date}")

        # Формируем параметры для API (произвольный период)
        date_str = target_date.strftime('%Y-%m-%d')

        # Запрос к API за конкретный день (только кампании с трафиком)
        raw_campaigns = self.client.get_campaigns(
            date="12",  # произвольный период (ВАЖНО: строка!)
            date_start=date_str,
            date_end=date_str,
            status=2,
            val_page="all"
        )

        cleaned = clean_campaigns_list(raw_campaigns)
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'zero_records': 0}

        with session_scope() as session:
            snapshot_time = get_now()

            # Словарь для быстрого поиска данных по binom_id
            campaigns_data_map = {}
            for camp_data in cleaned:
                camp_data = normalize_campaign_data(camp_data)
                binom_id = camp_data['id']
                campaigns_data_map[binom_id] = camp_data

            # Если передан список campaign_ids - обрабатываем ВСЕ кампании из списка
            if campaign_ids:
                logger.info(f"Processing {len(campaign_ids)} campaigns (creating zeros for missing)")

                for binom_id in campaign_ids:
                    # Находим кампанию в БД
                    campaign = session.query(Campaign).filter_by(binom_id=binom_id).first()

                    if not campaign:
                        # Кампания не существует в базе - пропускаем
                        logger.debug(f"Campaign {binom_id} not found in DB, skipping")
                        stats['skipped'] += 1
                        continue

                    # Проверяем есть ли данные от Binom
                    camp_data = campaigns_data_map.get(binom_id)

                    if camp_data:
                        # Есть данные от Binom - сохраняем
                        clicks = camp_data.get('clicks', 0)
                        leads = camp_data.get('leads', 0)
                        cost = camp_data.get('cost', 0)
                        revenue = camp_data.get('revenue', 0)
                        roi = camp_data.get('roi')
                        cr = camp_data.get('cr')
                        cpc = camp_data.get('cpc')
                        approve = camp_data.get('approve')
                        a_leads = camp_data.get('a_leads', 0)
                        h_leads = camp_data.get('h_leads', 0)
                        r_leads = camp_data.get('r_leads', 0)
                        lead_price = camp_data.get('lead')
                        profit = camp_data.get('profit')
                        epc = camp_data.get('epc')
                    else:
                        # Нет данных от Binom - записываем НУЛИ
                        clicks = 0
                        leads = 0
                        cost = 0.0
                        revenue = 0.0
                        roi = None
                        cr = None
                        cpc = None
                        approve = None
                        a_leads = 0
                        h_leads = 0
                        r_leads = 0
                        lead_price = None
                        profit = None
                        epc = None
                        stats['zero_records'] += 1

                    # Ищем существующую запись статистики за этот день
                    existing_stat = session.query(CampaignStatsDaily).filter_by(
                        campaign_id=campaign.internal_id,
                        date=target_date
                    ).first()

                    if existing_stat:
                        # Обновляем существующую
                        existing_stat.clicks = clicks
                        existing_stat.leads = leads
                        existing_stat.cost = cost
                        existing_stat.revenue = revenue
                        existing_stat.roi = roi
                        existing_stat.cr = cr
                        existing_stat.cpc = cpc
                        existing_stat.approve = approve
                        existing_stat.a_leads = a_leads
                        existing_stat.h_leads = h_leads
                        existing_stat.r_leads = r_leads
                        existing_stat.lead_price = lead_price
                        existing_stat.profit = profit
                        existing_stat.epc = epc
                        existing_stat.snapshot_time = snapshot_time
                        stats['updated'] += 1
                    else:
                        # Создаем новую
                        new_stat = CampaignStatsDaily(
                            campaign_id=campaign.internal_id,
                            date=target_date,
                            clicks=clicks,
                            leads=leads,
                            cost=cost,
                            revenue=revenue,
                            roi=roi,
                            cr=cr,
                            cpc=cpc,
                            approve=approve,
                            a_leads=a_leads,
                            h_leads=h_leads,
                            r_leads=r_leads,
                            lead_price=lead_price,
                            profit=profit,
                            epc=epc,
                            snapshot_time=snapshot_time
                        )
                        session.add(new_stat)
                        stats['created'] += 1

            else:
                # СТАРАЯ ЛОГИКА (без списка campaign_ids)
                logger.info(f"Processing {len(cleaned)} campaigns (old logic)")

                for camp_data in cleaned:
                    camp_data = normalize_campaign_data(camp_data)
                    binom_id = camp_data['id']
                    clicks = camp_data.get('clicks', 0)

                    # Фильтр: пропускаем если нет кликов
                    if clicks == 0:
                        stats['skipped'] += 1
                        continue

                    # Находим кампанию по binom_id
                    campaign = session.query(Campaign).filter_by(binom_id=binom_id).first()

                    if not campaign:
                        logger.debug(f"Campaign {binom_id} not found in DB, skipping daily stats")
                        stats['skipped'] += 1
                        continue

                    # Ищем существующую запись статистики за этот день
                    existing_stat = session.query(CampaignStatsDaily).filter_by(
                        campaign_id=campaign.internal_id,
                        date=target_date
                    ).first()

                    if existing_stat:
                        # Обновляем существующую
                        existing_stat.clicks = clicks
                        existing_stat.leads = camp_data.get('leads', 0)
                        existing_stat.cost = camp_data.get('cost', 0)
                        existing_stat.revenue = camp_data.get('revenue', 0)
                        existing_stat.roi = camp_data.get('roi')
                        existing_stat.cr = camp_data.get('cr')
                        existing_stat.cpc = camp_data.get('cpc')
                        existing_stat.approve = camp_data.get('approve')
                        existing_stat.a_leads = camp_data.get('a_leads', 0)
                        existing_stat.h_leads = camp_data.get('h_leads', 0)
                        existing_stat.r_leads = camp_data.get('r_leads', 0)
                        existing_stat.lead_price = camp_data.get('lead')
                        existing_stat.profit = camp_data.get('profit')
                        existing_stat.epc = camp_data.get('epc')
                        existing_stat.snapshot_time = snapshot_time
                        stats['updated'] += 1
                    else:
                        # Создаем новую
                        new_stat = CampaignStatsDaily(
                            campaign_id=campaign.internal_id,
                            date=target_date,
                            clicks=clicks,
                            leads=camp_data.get('leads', 0),
                            cost=camp_data.get('cost', 0),
                            revenue=camp_data.get('revenue', 0),
                            roi=camp_data.get('roi'),
                            cr=camp_data.get('cr'),
                            cpc=camp_data.get('cpc'),
                            approve=camp_data.get('approve'),
                            a_leads=camp_data.get('a_leads', 0),
                            h_leads=camp_data.get('h_leads', 0),
                            r_leads=camp_data.get('r_leads', 0),
                            lead_price=camp_data.get('lead'),
                            profit=camp_data.get('profit'),
                            epc=camp_data.get('epc'),
                            snapshot_time=snapshot_time
                        )
                        session.add(new_stat)
                        stats['created'] += 1

            session.commit()

        logger.info(f"Campaign daily stats for {target_date}: created={stats['created']}, updated={stats['updated']}, skipped={stats['skipped']}, zero_records={stats['zero_records']}")
        return stats

    def _collect_ts_daily_stats(self, target_date: date) -> Dict[str, int]:
        """
        Собирает дневную статистику по источникам трафика за конкретный день

        Args:
            target_date: дата для сбора

        Returns:
            Статистика: created, updated, skipped
        """
        logger.info(f"Collecting traffic source daily stats for {target_date}")

        date_str = target_date.strftime('%Y-%m-%d')

        raw_ts = self.client.get_traffic_sources(
            date="12",
            date_start=date_str,
            date_end=date_str,
            status=2,
            val_page="all"
        )

        cleaned = clean_traffic_sources_list(raw_ts)
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        with session_scope() as session:
            snapshot_time = get_now()

            for ts_data in cleaned:
                ts_data = normalize_traffic_source_data(ts_data)
                ts_id = ts_data['id']
                clicks = ts_data.get('clicks', 0)

                if clicks == 0:
                    stats['skipped'] += 1
                    continue

                # Проверяем существование TS в базе
                ts = session.query(TrafficSource).filter_by(id=ts_id).first()
                if not ts:
                    logger.debug(f"TrafficSource {ts_id} not found in DB, skipping daily stats")
                    stats['skipped'] += 1
                    continue

                # Ищем/создаем запись статистики
                existing = session.query(TrafficSourceStatsDaily).filter_by(
                    ts_id=ts_id,
                    date=target_date
                ).first()

                if existing:
                    # Обновляем
                    existing.clicks = clicks
                    existing.cost = ts_data.get('cost', 0)
                    existing.leads = ts_data.get('leads', 0)
                    existing.revenue = ts_data.get('revenue', 0)
                    existing.roi = ts_data.get('roi')
                    existing.cr = ts_data.get('cr')
                    existing.cpc = ts_data.get('cpc')
                    existing.a_leads = ts_data.get('a_leads', 0)
                    existing.h_leads = ts_data.get('h_leads', 0)
                    existing.r_leads = ts_data.get('r_leads', 0)
                    existing.approve = ts_data.get('approve')
                    existing.active_campaigns = ts_data.get('campaigns', 0)
                    existing.snapshot_time = snapshot_time
                    stats['updated'] += 1
                else:
                    # Создаем новую
                    new_stat = TrafficSourceStatsDaily(
                        ts_id=ts_id,
                        date=target_date,
                        clicks=clicks,
                        cost=ts_data.get('cost', 0),
                        leads=ts_data.get('leads', 0),
                        revenue=ts_data.get('revenue', 0),
                        roi=ts_data.get('roi'),
                        cr=ts_data.get('cr'),
                        cpc=ts_data.get('cpc'),
                        a_leads=ts_data.get('a_leads', 0),
                        h_leads=ts_data.get('h_leads', 0),
                        r_leads=ts_data.get('r_leads', 0),
                        approve=ts_data.get('approve'),
                        active_campaigns=ts_data.get('campaigns', 0),
                        snapshot_time=snapshot_time
                    )
                    session.add(new_stat)
                    stats['created'] += 1

            session.commit()

        logger.info(f"TS daily stats for {target_date}: created={stats['created']}, updated={stats['updated']}, skipped={stats['skipped']}")
        return stats

    def _collect_offer_daily_stats(self, target_date: date) -> Dict[str, int]:
        """
        Собирает дневную статистику по офферам за конкретный день

        Args:
            target_date: дата для сбора

        Returns:
            Статистика: created, updated, skipped
        """
        logger.info(f"Collecting offer daily stats for {target_date}")

        date_str = target_date.strftime('%Y-%m-%d')

        raw_offers = self.client.get_offers(
            date="12",
            date_start=date_str,
            date_end=date_str,
            status=2,
            val_page="all"
        )

        cleaned = clean_offers_list(raw_offers)
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        with session_scope() as session:
            snapshot_time = get_now()

            for offer_data in cleaned:
                offer_data = normalize_offer_data(offer_data)
                offer_id = offer_data['id']
                clicks = offer_data.get('clicks', 0)

                if clicks == 0:
                    stats['skipped'] += 1
                    continue

                # Проверяем существование оффера
                offer = session.query(Offer).filter_by(id=offer_id).first()
                if not offer:
                    logger.debug(f"Offer {offer_id} not found in DB, skipping daily stats")
                    stats['skipped'] += 1
                    continue

                # Ищем/создаем запись статистики
                existing = session.query(OfferStatsDaily).filter_by(
                    offer_id=offer_id,
                    date=target_date
                ).first()

                if existing:
                    # Обновляем
                    existing.clicks = clicks
                    existing.leads = offer_data.get('leads', 0)
                    existing.revenue = offer_data.get('revenue', 0)
                    existing.cost = offer_data.get('cost', 0)
                    existing.a_leads = offer_data.get('a_leads', 0)
                    existing.h_leads = offer_data.get('h_leads', 0)
                    existing.r_leads = offer_data.get('r_leads', 0)
                    existing.cr = offer_data.get('cr')
                    existing.approve = offer_data.get('approve')
                    existing.epc = offer_data.get('epc')
                    existing.roi = offer_data.get('roi')
                    existing.snapshot_time = snapshot_time
                    stats['updated'] += 1
                else:
                    # Создаем новую
                    new_stat = OfferStatsDaily(
                        offer_id=offer_id,
                        date=target_date,
                        clicks=clicks,
                        leads=offer_data.get('leads', 0),
                        revenue=offer_data.get('revenue', 0),
                        cost=offer_data.get('cost', 0),
                        a_leads=offer_data.get('a_leads', 0),
                        h_leads=offer_data.get('h_leads', 0),
                        r_leads=offer_data.get('r_leads', 0),
                        cr=offer_data.get('cr'),
                        approve=offer_data.get('approve'),
                        epc=offer_data.get('epc'),
                        roi=offer_data.get('roi'),
                        snapshot_time=snapshot_time
                    )
                    session.add(new_stat)
                    stats['created'] += 1

            session.commit()

        logger.info(f"Offer daily stats for {target_date}: created={stats['created']}, updated={stats['updated']}, skipped={stats['skipped']}")
        return stats

    def _collect_network_daily_stats(self, target_date: date) -> Dict[str, int]:
        """
        Собирает дневную статистику по партнеркам за конкретный день

        Args:
            target_date: дата для сбора

        Returns:
            Статистика: created, updated, skipped
        """
        logger.info(f"Collecting network daily stats for {target_date}")

        date_str = target_date.strftime('%Y-%m-%d')

        raw_networks = self.client.get_affiliate_networks(
            date="12",
            date_start=date_str,
            date_end=date_str,
            status=2,
            val_page="all"
        )

        cleaned = clean_affiliate_networks_list(raw_networks)
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        with session_scope() as session:
            snapshot_time = get_now()

            for net_data in cleaned:
                net_data = normalize_affiliate_network_data(net_data)
                net_id = net_data['id']
                clicks = net_data.get('clicks', 0)

                if clicks == 0:
                    stats['skipped'] += 1
                    continue

                # Проверяем существование сети
                network = session.query(AffiliateNetwork).filter_by(id=net_id).first()
                if not network:
                    logger.debug(f"Network {net_id} not found in DB, skipping daily stats")
                    stats['skipped'] += 1
                    continue

                # Ищем/создаем запись статистики
                existing = session.query(NetworkStatsDaily).filter_by(
                    network_id=net_id,
                    date=target_date
                ).first()

                if existing:
                    # Обновляем
                    existing.clicks = clicks
                    existing.leads = net_data.get('leads', 0)
                    existing.revenue = net_data.get('revenue', 0)
                    existing.cost = net_data.get('cost', 0)
                    existing.a_leads = net_data.get('a_leads', 0)
                    existing.h_leads = net_data.get('h_leads', 0)
                    existing.r_leads = net_data.get('r_leads', 0)
                    existing.approve = net_data.get('approve')
                    existing.roi = net_data.get('roi')
                    existing.profit = net_data.get('profit')
                    existing.active_offers = net_data.get('offers', 0)
                    existing.snapshot_time = snapshot_time
                    stats['updated'] += 1
                else:
                    # Создаем новую
                    new_stat = NetworkStatsDaily(
                        network_id=net_id,
                        date=target_date,
                        clicks=clicks,
                        leads=net_data.get('leads', 0),
                        revenue=net_data.get('revenue', 0),
                        cost=net_data.get('cost', 0),
                        a_leads=net_data.get('a_leads', 0),
                        h_leads=net_data.get('h_leads', 0),
                        r_leads=net_data.get('r_leads', 0),
                        approve=net_data.get('approve'),
                        roi=net_data.get('roi'),
                        profit=net_data.get('profit'),
                        active_offers=net_data.get('offers', 0),
                        snapshot_time=snapshot_time
                    )
                    session.add(new_stat)
                    stats['created'] += 1

            session.commit()

        logger.info(f"Network daily stats for {target_date}: created={stats['created']}, updated={stats['updated']}, skipped={stats['skipped']}")
        return stats

    # ========================================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ ДЛЯ ЗАПУСКА СБОРА
    # ========================================================================

    def initial_collect(self, days: int = 60) -> Dict[str, Any]:
        """
        Первичный сбор данных за последние N дней

        ПРОЦЕСС (ИСПРАВЛЕННАЯ ВЕРСИЯ):
        1. Собирает мета-информацию (кампании, TS, офферы, партнерки)
        2. Получает список всех IDs за период (для создания записей с нулями)
        3. Для каждого дня за период собирает дневную статистику с нулями
        4. Паузы 2 минуты между типами сущностей

        Args:
            days: количество дней для сбора (по умолчанию 60)

        Returns:
            Полная статистика сбора
        """
        logger.info("=" * 80)
        logger.info(f"Starting INITIAL data collection for last {days} days (FIXED VERSION)")
        logger.info("=" * 80)

        start_time = get_now()
        dates = self._generate_date_range(days)

        logger.info(f"Will collect data for {len(dates)} days: {dates[0]} to {dates[-1]}")

        # ЭТАП 1: Собираем мета-информацию за все дни разом
        logger.info("\n" + "=" * 80)
        logger.info("STAGE 1: Collecting meta-information (entities)")
        logger.info("=" * 80)

        campaigns_meta = self._collect_campaigns_block(period_days=days)
        time.sleep(self.pause_between_blocks)

        ts_meta = self._collect_traffic_sources_block(period_days=days)
        time.sleep(self.pause_between_blocks)

        offers_meta = self._collect_offers_block(period_days=days)
        time.sleep(self.pause_between_blocks)

        networks_meta = self._collect_networks_block(period_days=days)

        # ЭТАП 1.5: Получаем списки всех IDs за период (для создания записей с нулями)
        logger.info("\n" + "=" * 80)
        logger.info("STAGE 1.5: Getting all IDs for period")
        logger.info("=" * 80)

        campaign_ids = self._get_all_campaign_ids_for_period(days)
        logger.info(f"Will create daily records for {len(campaign_ids)} campaigns")
        time.sleep(self.pause_between_blocks)

        # TODO: Добавить аналогичные методы для TS, Offers, Networks
        # ts_ids = self._get_all_ts_ids_for_period(days)
        # offer_ids = self._get_all_offer_ids_for_period(days)
        # network_ids = self._get_all_network_ids_for_period(days)

        # ЭТАП 2: Собираем дневную статистику по каждому дню
        logger.info("\n" + "=" * 80)
        logger.info(f"STAGE 2: Collecting daily stats for {len(dates)} days")
        logger.info("=" * 80)

        daily_stats_summary = {
            'campaigns': {'created': 0, 'updated': 0, 'skipped': 0, 'zero_records': 0},
            'traffic_sources': {'created': 0, 'updated': 0, 'skipped': 0},
            'offers': {'created': 0, 'updated': 0, 'skipped': 0},
            'networks': {'created': 0, 'updated': 0, 'skipped': 0}
        }

        for day_num, target_date in enumerate(dates, 1):
            logger.info(f"\n--- Day {day_num}/{len(dates)}: {target_date} ---")

            # Campaigns daily stats (с нулями для отсутствующих)
            camp_stats = self._collect_campaign_daily_stats(target_date, campaign_ids=campaign_ids)
            for k, v in camp_stats.items():
                if k in daily_stats_summary['campaigns']:
                    daily_stats_summary['campaigns'][k] += v
            time.sleep(self.pause_between_blocks)

            # Traffic Sources daily stats (пока старая логика)
            ts_stats = self._collect_ts_daily_stats(target_date)
            for k, v in ts_stats.items():
                daily_stats_summary['traffic_sources'][k] += v
            time.sleep(self.pause_between_blocks)

            # Offers daily stats (пока старая логика)
            offer_stats = self._collect_offer_daily_stats(target_date)
            for k, v in offer_stats.items():
                daily_stats_summary['offers'][k] += v
            time.sleep(self.pause_between_blocks)

            # Networks daily stats (пока старая логика)
            net_stats = self._collect_network_daily_stats(target_date)
            for k, v in net_stats.items():
                daily_stats_summary['networks'][k] += v

            # Пауза между днями (только если это не последний день)
            if day_num < len(dates):
                time.sleep(self.pause_between_blocks)

        # Итоговая статистика
        duration = (get_now() - start_time).total_seconds()

        result = {
            'type': 'initial_collect',
            'days_collected': days,
            'date_range': {
                'start': dates[0].isoformat(),
                'end': dates[-1].isoformat()
            },
            'meta_info': {
                'campaigns': campaigns_meta,
                'traffic_sources': ts_meta,
                'offers': offers_meta,
                'networks': networks_meta
            },
            'daily_stats': daily_stats_summary,
            'duration_seconds': duration,
            'duration_minutes': round(duration / 60, 2)
        }

        logger.info("\n" + "=" * 80)
        logger.info("INITIAL COLLECTION COMPLETED")
        logger.info("=" * 80)
        logger.info(f"Duration: {result['duration_minutes']} minutes")
        logger.info(f"Campaigns meta: {campaigns_meta}")
        logger.info(f"Campaigns daily: {daily_stats_summary['campaigns']}")
        logger.info(f"Traffic Sources meta: {ts_meta}")
        logger.info(f"Traffic Sources daily: {daily_stats_summary['traffic_sources']}")
        logger.info(f"Offers meta: {offers_meta}")
        logger.info(f"Offers daily: {daily_stats_summary['offers']}")
        logger.info(f"Networks meta: {networks_meta}")
        logger.info(f"Networks daily: {daily_stats_summary['networks']}")

        return result
