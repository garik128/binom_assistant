"""
Утилита для очистки старых данных из БД

Удаляет дневную статистику старше указанного количества дней
для освобождения места и повышения производительности.

Использование:
    from services.scheduler.cleanup import cleanup_old_data
    cleanup_old_data(days_to_keep=90)
"""
import logging
from datetime import date, timedelta
from typing import Dict, Any

from storage.database import (
    session_scope,
    CampaignStatsDaily,
    TrafficSourceStatsDaily,
    OfferStatsDaily,
    NetworkStatsDaily
)

logger = logging.getLogger(__name__)


def cleanup_old_data(days_to_keep: int = 90) -> Dict[str, Any]:
    """
    Удаляет дневную статистику старше X дней

    Args:
        days_to_keep: сколько дней хранить (по умолчанию 90)

    Returns:
        Словарь со статистикой удаления:
        {
            'cutoff_date': date,
            'deleted': {
                'campaign_stats': int,
                'ts_stats': int,
                'offer_stats': int,
                'network_stats': int,
                'total': int
            },
            'errors': []
        }
    """
    cutoff_date = date.today() - timedelta(days=days_to_keep)

    stats = {
        'cutoff_date': cutoff_date,
        'deleted': {
            'campaign_stats': 0,
            'ts_stats': 0,
            'offer_stats': 0,
            'network_stats': 0,
            'total': 0
        },
        'errors': []
    }

    logger.info(f"Starting cleanup: removing data older than {cutoff_date}")

    try:
        with session_scope() as session:
            # 1. Удаляем старые campaign_stats_daily
            try:
                deleted_campaign_stats = session.query(CampaignStatsDaily).filter(
                    CampaignStatsDaily.date < cutoff_date
                ).delete(synchronize_session=False)

                stats['deleted']['campaign_stats'] = deleted_campaign_stats
                logger.info(f"Deleted {deleted_campaign_stats} campaign daily stats")
            except Exception as e:
                error_msg = f"Error deleting campaign stats: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

            # 2. Удаляем старые traffic_source_stats_daily
            try:
                deleted_ts_stats = session.query(TrafficSourceStatsDaily).filter(
                    TrafficSourceStatsDaily.date < cutoff_date
                ).delete(synchronize_session=False)

                stats['deleted']['ts_stats'] = deleted_ts_stats
                logger.info(f"Deleted {deleted_ts_stats} traffic source daily stats")
            except Exception as e:
                error_msg = f"Error deleting TS stats: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

            # 3. Удаляем старые offer_stats_daily
            try:
                deleted_offer_stats = session.query(OfferStatsDaily).filter(
                    OfferStatsDaily.date < cutoff_date
                ).delete(synchronize_session=False)

                stats['deleted']['offer_stats'] = deleted_offer_stats
                logger.info(f"Deleted {deleted_offer_stats} offer daily stats")
            except Exception as e:
                error_msg = f"Error deleting offer stats: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

            # 4. Удаляем старые network_stats_daily
            try:
                deleted_network_stats = session.query(NetworkStatsDaily).filter(
                    NetworkStatsDaily.date < cutoff_date
                ).delete(synchronize_session=False)

                stats['deleted']['network_stats'] = deleted_network_stats
                logger.info(f"Deleted {deleted_network_stats} network daily stats")
            except Exception as e:
                error_msg = f"Error deleting network stats: {e}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

            # Подсчитываем общее количество удаленных записей
            stats['deleted']['total'] = (
                stats['deleted']['campaign_stats'] +
                stats['deleted']['ts_stats'] +
                stats['deleted']['offer_stats'] +
                stats['deleted']['network_stats']
            )

            # Коммитим все изменения
            session.commit()

            # Запускаем VACUUM для освобождения места на диске (только для SQLite)
            try:
                from config import get_config
                config = get_config()
                if config.database_url.startswith('sqlite'):
                    logger.info("Running VACUUM to reclaim disk space...")
                    session.execute("VACUUM")
                    logger.info("VACUUM completed successfully")
            except Exception as vacuum_error:
                error_msg = f"VACUUM failed: {vacuum_error}"
                logger.warning(error_msg)
                stats['errors'].append(error_msg)

            logger.info(f"Cleanup completed: {stats['deleted']['total']} records deleted")

            if stats['errors']:
                logger.warning(f"Cleanup completed with {len(stats['errors'])} errors")

    except Exception as e:
        error_msg = f"Fatal error during cleanup: {e}"
        logger.error(error_msg, exc_info=True)
        stats['errors'].append(error_msg)

    return stats


def cleanup_very_old_data(days_to_keep: int = 180) -> Dict[str, Any]:
    """
    Агрессивная очистка для случаев когда БД слишком большая

    Args:
        days_to_keep: сколько дней хранить (по умолчанию 180)

    Returns:
        Статистика удаления
    """
    logger.warning(f"Running AGGRESSIVE cleanup with {days_to_keep} days retention")
    return cleanup_old_data(days_to_keep=days_to_keep)


if __name__ == '__main__':
    # Настраиваем логирование для standalone запуска
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Запускаем очистку с параметрами по умолчанию
    result = cleanup_old_data(days_to_keep=90)

    print("\n" + "="*60)
    print("CLEANUP RESULTS")
    print("="*60)
    print(f"Cutoff date: {result['cutoff_date']}")
    print(f"\nDeleted records:")
    print(f"  - Campaign stats:      {result['deleted']['campaign_stats']:,}")
    print(f"  - Traffic Source stats: {result['deleted']['ts_stats']:,}")
    print(f"  - Offer stats:         {result['deleted']['offer_stats']:,}")
    print(f"  - Network stats:       {result['deleted']['network_stats']:,}")
    print(f"  - TOTAL:               {result['deleted']['total']:,}")

    if result['errors']:
        print(f"\nErrors encountered: {len(result['errors'])}")
        for error in result['errors']:
            print(f"  - {error}")

    print("="*60)
