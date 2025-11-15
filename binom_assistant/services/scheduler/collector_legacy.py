"""
Сборщик данных из Binom API

Отвечает за:
- Ежедневный сбор данных за последние 7 дней
- Обновление существующих записей (апрувы задним числом)
- Определение типа кампаний (CPL/CPA)
- Сохранение в БД
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.exc import IntegrityError

from core.api_client import BinomClient, CPLDetector, clean_campaign_data, clean_campaign_stats
from storage.database import (
    session_scope,
    Campaign,
    CampaignStatsDaily,
    StatPeriod,
    NameChange
)


logger = logging.getLogger(__name__)


class DataCollector:
    """
    Сборщик данных из Binom

    Использование:
        collector = DataCollector()
        collector.daily_collect()
    """

    def __init__(self):
        """Инициализация сборщика"""
        self.client = BinomClient()
        self.cpl_detector = CPLDetector()
        logger.info("DataCollector initialized")

    def _update_campaign_status(self, campaign, session):
        """
        Автоматически определяет статус кампании

        Логика:
        - Если cost не изменился за последние 2 дня = пауза
        - Если есть расходы = активна

        Args:
            campaign: объект Campaign
            session: сессия БД
        """
        # Получаем статистику за последние 2 дня
        two_days_ago = date.today() - timedelta(days=2)

        stats_2days = session.query(CampaignStatsDaily).filter(
            CampaignStatsDaily.campaign_id == campaign.internal_id,
            CampaignStatsDaily.date >= two_days_ago
        ).order_by(CampaignStatsDaily.date.desc()).limit(2).all()

        if len(stats_2days) >= 2:
            # Сравниваем cost
            if stats_2days[0].cost == 0 and stats_2days[1].cost == 0:
                # Нет расходов = пауза
                campaign.is_active = False
                campaign.status = 'paused'
                logger.debug(f"Campaign {campaign.binom_id} marked as paused (no cost)")
            elif float(stats_2days[0].cost) > 0:
                # Есть расходы = активна
                campaign.is_active = True
                campaign.status = 'active'
                logger.debug(f"Campaign {campaign.binom_id} marked as active")
        elif len(stats_2days) == 1:
            # Есть данные только за 1 день
            if float(stats_2days[0].cost) > 0:
                campaign.is_active = True
                campaign.status = 'active'
            else:
                campaign.is_active = False
                campaign.status = 'paused'

    def daily_collect(self) -> Dict[str, Any]:
        """
        Ежедневный сбор данных

        СТРАТЕГИЯ СБОРА (8 запросов вместо 362):
        1. Получаем список кампаний за месяц (stats_period) - 1 запрос
        2. Получаем дневную статистику за последние 7 дней (stats_daily) - 7 запросов
           Каждый запрос возвращает ВСЕ кампании за конкретный день

        ВАЖНО: апрувы прилетают задним числом, поэтому обновляем последние 7 дней

        Returns:
            Словарь со статистикой сбора
        """
        logger.info("=" * 60)
        logger.info("Starting daily data collection")
        logger.info("=" * 60)

        start_time = datetime.now()

        # Статистика
        stats = {
            'campaigns_processed': 0,
            'campaigns_new': 0,
            'campaigns_updated': 0,
            'stats_records_new': 0,
            'stats_records_updated': 0,
            'stats_daily_new': 0,
            'stats_daily_updated': 0,
            'name_changes': 0,
            'cpl_detected': 0,
            'errors': 0,
            'start_time': start_time,
            'end_time': None,
            'duration_seconds': 0
        }

        try:
            # ==========================================
            # ЭТАП 1: Получаем список кампаний за месяц
            # ==========================================
            logger.info("Step 1: Fetching campaigns list for current month (stats_period)")

            all_campaigns_seen = set()  # Отслеживаем уникальные кампании

            period_type = '7days'
            date_param = "3"
            logger.info(f"Fetching campaigns for period: {period_type} (date={date_param})...")

            campaigns_raw = self.client.get_campaigns(
                date=date_param,
                status=2,
                val_page="all"
            )

            if not campaigns_raw:
                logger.warning(f"No campaigns for {period_type}")
            else:
                logger.info(f"Received {len(campaigns_raw)} campaigns for {period_type}")

                # 2. Обрабатываем каждую кампанию
                for raw_campaign in campaigns_raw:
                    try:
                        campaign_data = clean_campaign_data(raw_campaign)
                        campaign_id = campaign_data['id']

                        # Фильтрация: пропускаем кампании с нулевыми данными
                        # (кампании без трафика в периоде не представляют ценности)
                        clicks = campaign_data.get('clicks', 0)
                        cost = campaign_data.get('cost', 0)
                        if clicks == 0 and cost == 0:
                            logger.debug(f"Skipping campaign {campaign_id} - no traffic (clicks=0, cost=0)")
                            continue

                        # Обрабатываем мета-инфо кампании только один раз
                        if campaign_id not in all_campaigns_seen:
                            result = self._process_campaign(campaign_data, period_type)
                            all_campaigns_seen.add(campaign_id)

                            if result['is_new']:
                                stats['campaigns_new'] += 1
                            else:
                                stats['campaigns_updated'] += 1

                            if result['name_changed']:
                                stats['name_changes'] += 1

                            if result['is_cpl']:
                                stats['cpl_detected'] += 1

                            # ВАЖНО: детальная статистика по дням (StatDaily) НЕ собирается при каждом запуске
                            # Это делается по требованию через agent_tools для экономии запросов к API
                            # Агрегированные данные за период уже сохранены в StatPeriod

                            # Обновляем статус кампании на основе последних данных
                            with session_scope() as session:
                                campaign = session.query(Campaign).filter_by(binom_id=campaign_id).first()
                                if campaign:
                                    self._update_campaign_status(campaign, session)
                                    session.commit()
                        else:
                            # Кампания уже обработана, только сохраняем данные за период
                            with session_scope() as session:
                                campaign = session.query(Campaign).filter_by(binom_id=campaign_id).first()
                                if campaign:
                                    self._save_period_stats(session, campaign.internal_id, campaign_data, period_type, datetime.now())
                                    session.commit()

                        stats['stats_records_new'] += 1

                    except Exception as e:
                        logger.error(f"Error processing campaign {raw_campaign.get('id')}: {e}")
                        stats['errors'] += 1

            stats['campaigns_processed'] = len(all_campaigns_seen)

            # 3. Финализация
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            stats['end_time'] = end_time
            stats['duration_seconds'] = duration

            logger.info("=" * 60)
            logger.info("Daily collection completed")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Campaigns: {stats['campaigns_processed']} processed")
            logger.info(f"  New: {stats['campaigns_new']}")
            logger.info(f"  Updated: {stats['campaigns_updated']}")
            logger.info(f"  CPL detected: {stats['cpl_detected']}")
            logger.info(f"Stats records: {stats['stats_records_new']} new, {stats['stats_records_updated']} updated")
            logger.info(f"Errors: {stats['errors']}")
            logger.info("=" * 60)

            return stats

        except Exception as e:
            logger.error(f"Fatal error in daily_collect: {e}")
            stats['errors'] += 1
            return stats

    def _process_campaign(self, campaign_data: Dict[str, Any], period_type: str = '7days') -> Dict[str, bool]:
        """
        Обрабатывает одну кампанию и сохраняет агрегированные данные

        Args:
            campaign_data: очищенные данные кампании
            period_type: тип периода ('today', '7days', '14days', '30days')

        Returns:
            Словарь с результатами обработки
        """
        binom_id = campaign_data['id']
        current_name = campaign_data['name']

        result = {
            'is_new': False,
            'name_changed': False,
            'is_cpl': False
        }

        with session_scope() as session:
            # Ищем кампанию в БД
            campaign = session.query(Campaign).filter_by(
                binom_id=binom_id
            ).first()

            now = datetime.now()

            if not campaign:
                # Новая кампания
                logger.info(f"New campaign: {binom_id} - {current_name}")

                campaign = Campaign(
                    binom_id=binom_id,
                    current_name=current_name,
                    group_name=campaign_data.get('group_name', ''),
                    ts_name=campaign_data.get('ts_name', ''),
                    domain_name=campaign_data.get('domain_name', ''),
                    is_cpl_mode=False,
                    is_active=True,
                    status='active',
                    first_seen=now,
                    last_seen=now
                )

                session.add(campaign)
                session.flush()  # Получаем ID

                result['is_new'] = True

            else:
                # Обновляем существующую
                campaign.last_seen = now

                # Проверяем изменение имени
                if campaign.current_name != current_name:
                    logger.info(
                        f"Name changed for {binom_id}: "
                        f"'{campaign.current_name}' -> '{current_name}'"
                    )

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

                # Обновляем группы
                campaign.group_name = campaign_data.get('group_name', '')
                campaign.ts_name = campaign_data.get('ts_name', '')
                campaign.domain_name = campaign_data.get('domain_name', '')

            # Определяем тип кампании (CPL/CPA)
            is_cpl = self.cpl_detector.detect(campaign_data)
            campaign.is_cpl_mode = is_cpl
            result['is_cpl'] = is_cpl

            # Сохраняем агрегированные данные за период
            self._save_period_stats(session, campaign.internal_id, campaign_data, period_type, now)

            session.commit()

        return result

    def _save_period_stats(
        self,
        session,
        campaign_id: int,
        campaign_data: Dict[str, Any],
        period_type: str,
        snapshot_time: datetime
    ) -> None:
        """
        Сохраняет агрегированную статистику за период

        Args:
            session: сессия БД
            campaign_id: ID кампании в БД
            campaign_data: данные кампании
            period_type: тип периода
            snapshot_time: время снимка
        """
        # Вычисляем период (период_start, период_end)
        today = date.today()
        if period_type == 'today':
            period_start = period_end = today
        elif period_type == '7days':
            period_start = today - timedelta(days=6)
            period_end = today
        elif period_type == '14days':
            period_start = today - timedelta(days=13)
            period_end = today
        elif period_type == '30days':
            period_start = today - timedelta(days=29)
            period_end = today
        else:
            # произвольный период
            period_start = period_end = today

        # Ищем существующую запись
        existing = session.query(StatPeriod).filter_by(
            campaign_id=campaign_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end
        ).first()

        if existing:
            # Обновляем существующую
            existing.clicks = campaign_data.get('clicks', 0)
            existing.leads = campaign_data.get('leads', 0)
            existing.cost = campaign_data.get('cost', 0)
            existing.revenue = campaign_data.get('revenue', 0)
            existing.roi = campaign_data.get('roi')
            existing.cr = campaign_data.get('cr')
            existing.cpc = campaign_data.get('cpc')
            existing.approve = campaign_data.get('approve')
            existing.a_leads = campaign_data.get('a_leads', 0)
            existing.h_leads = campaign_data.get('h_leads', 0)
            existing.r_leads = campaign_data.get('r_leads', 0)
            existing.lead_price = campaign_data.get('lead')
            existing.profit = campaign_data.get('profit')
            existing.epc = campaign_data.get('epc')
            existing.snapshot_time = snapshot_time
            logger.debug(f"Updated period stats for campaign {campaign_id}")
        else:
            # Создаем новую
            new_stat = StatPeriod(
                campaign_id=campaign_id,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                clicks=campaign_data.get('clicks', 0),
                leads=campaign_data.get('leads', 0),
                cost=campaign_data.get('cost', 0),
                revenue=campaign_data.get('revenue', 0),
                roi=campaign_data.get('roi'),
                cr=campaign_data.get('cr'),
                cpc=campaign_data.get('cpc'),
                approve=campaign_data.get('approve'),
                a_leads=campaign_data.get('a_leads', 0),
                h_leads=campaign_data.get('h_leads', 0),
                r_leads=campaign_data.get('r_leads', 0),
                lead_price=campaign_data.get('lead'),
                profit=campaign_data.get('profit'),
                epc=campaign_data.get('epc'),
                snapshot_time=snapshot_time
            )
            session.add(new_stat)
            logger.debug(f"Created new period stats for campaign {campaign_id}")

    def _collect_campaign_stats(
        self,
        binom_id: int,
        stats: Dict[str, Any]
    ) -> None:
        """
        Собирает детальную статистику по кампании

        Args:
            binom_id: ID кампании в Binom
            stats: словарь для обновления статистики
        """
        # Получаем статистику по дням за текущий месяц
        stats_raw = self.client.get_campaign_stats(
            camp_id=binom_id,
            date="5",      # текущий месяц (date=5)
            group1="31",   # группировка по дням
            val_page="all"
        )

        if not stats_raw:
            return

        # Обрабатываем каждый день
        for raw_stat in stats_raw:
            try:
                # Очищаем данные
                stat_data = clean_campaign_stats(raw_stat)

                # Сохраняем в БД
                is_new = self._save_daily_stat(binom_id, stat_data)

                if is_new:
                    stats['stats_records_new'] += 1
                else:
                    stats['stats_records_updated'] += 1

            except Exception as e:
                logger.error(f"Error processing stat for campaign {binom_id}: {e}")
                stats['errors'] += 1

    def _save_daily_stat(
        self,
        binom_id: int,
        stat_data: Dict[str, Any]
    ) -> bool:
        """
        Сохраняет дневную статистику в БД

        Args:
            binom_id: ID кампании в Binom
            stat_data: данные статистики

        Returns:
            True если создана новая запись, False если обновлена
        """
        with session_scope() as session:
            # Получаем кампанию
            campaign = session.query(Campaign).filter_by(
                binom_id=binom_id
            ).first()

            if not campaign:
                logger.warning(f"Campaign {binom_id} not found in DB")
                return False

            # Парсим дату из поля 'name' (обычно это дата в формате YYYY-MM-DD)
            date_str = stat_data.get('name', '')
            try:
                stat_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Invalid date format: {date_str}")
                return False

            # Ищем существующую запись
            existing = session.query(CampaignStatsDaily).filter_by(
                campaign_id=campaign.internal_id,
                date=stat_date
            ).first()

            snapshot_time = datetime.now()

            if existing:
                # Обновляем существующую запись
                existing.clicks = stat_data.get('clicks', 0)
                existing.leads = stat_data.get('leads', 0)
                existing.cost = stat_data.get('cost', 0)
                existing.revenue = stat_data.get('revenue', 0)
                existing.roi = stat_data.get('roi')
                existing.cr = stat_data.get('cr')
                existing.cpc = stat_data.get('cpc')
                existing.approve = stat_data.get('approve')
                existing.a_leads = stat_data.get('a_leads', 0)
                existing.h_leads = stat_data.get('h_leads', 0)
                existing.r_leads = stat_data.get('r_leads', 0)
                existing.lead_price = stat_data.get('lead')
                existing.profit = stat_data.get('profit')
                existing.epc = stat_data.get('epc')
                existing.snapshot_time = snapshot_time

                session.commit()
                logger.debug(f"Updated stat for campaign {binom_id} on {stat_date}")
                return False

            else:
                # Создаем новую запись
                new_stat = CampaignStatsDaily(
                    campaign_id=campaign.internal_id,
                    date=stat_date,
                    clicks=stat_data.get('clicks', 0),
                    leads=stat_data.get('leads', 0),
                    cost=stat_data.get('cost', 0),
                    revenue=stat_data.get('revenue', 0),
                    roi=stat_data.get('roi'),
                    cr=stat_data.get('cr'),
                    cpc=stat_data.get('cpc'),
                    approve=stat_data.get('approve'),
                    a_leads=stat_data.get('a_leads', 0),
                    h_leads=stat_data.get('h_leads', 0),
                    r_leads=stat_data.get('r_leads', 0),
                    lead_price=stat_data.get('lead'),
                    profit=stat_data.get('profit'),
                    epc=stat_data.get('epc'),
                    snapshot_time=snapshot_time
                )

                session.add(new_stat)
                session.commit()

                logger.debug(f"Created new stat for campaign {binom_id} on {stat_date}")
                return True

    def collect_specific_campaign(self, binom_id: int) -> bool:
        """
        Собирает данные по конкретной кампании

        Args:
            binom_id: ID кампании в Binom

        Returns:
            True если успешно, False при ошибке
        """
        logger.info(f"Collecting data for campaign {binom_id}")

        try:
            # Получаем данные кампании
            campaigns = self.client.get_campaigns(date="1", val_page="all")

            if not campaigns:
                return False

            # Ищем нужную кампанию
            campaign_data = None
            for camp in campaigns:
                if camp['id'] == binom_id:
                    campaign_data = clean_campaign_data(camp)
                    break

            if not campaign_data:
                logger.warning(f"Campaign {binom_id} not found in API response")
                return False

            # Обрабатываем
            self._process_campaign(campaign_data)

            # Собираем статистику
            stats = {
                'stats_records_new': 0,
                'stats_records_updated': 0,
                'errors': 0
            }
            self._collect_campaign_stats(binom_id, stats)

            logger.info(
                f"Campaign {binom_id} collected: "
                f"{stats['stats_records_new']} new, "
                f"{stats['stats_records_updated']} updated"
            )

            return True

        except Exception as e:
            logger.error(f"Error collecting campaign {binom_id}: {e}")
            return False
