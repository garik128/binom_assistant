"""
Модуль для определения типа оплаты кампаний

CPL (Cost Per Lead): оплата сразу за лид
- Примеры: мобильные подписки, некоторая нутра с прямой оплатой
- Признак: a_leads = 0, но revenue > 0

CPA (Cost Per Action): оплата после апрува
- Примеры: обычная нутра
- Признак: a_leads > 0 когда есть revenue
"""
import logging
from typing import Dict, Any, Optional, List

from storage.database import Campaign, get_session


logger = logging.getLogger(__name__)


class CPLDetector:
    """
    Детектор типа оплаты кампании

    Использование:
        detector = CPLDetector()
        is_cpl = detector.detect(campaign_data)
    """

    def __init__(self):
        """Инициализация детектора"""
        self.confidence_threshold = 0.8
        logger.debug("CPLDetector initialized")

    def detect(self, campaign_data: Dict[str, Any]) -> bool:
        """
        Определяет является ли кампания CPL-типом

        Логика определения:
        - CPL: revenue > 0, leads > 0, a_leads = 0, r_leads = 0
          (деньги есть, лиды есть, но нет апрувов и реджектов - значит платят сразу)

        - CPA: a_leads > 0 ИЛИ (a_leads = 0 И r_leads > 0)
          (есть апрувнутые лиды, или только отклоненные - значит система апрувов)

        Args:
            campaign_data: данные кампании с полями a_leads, r_leads, revenue, leads

        Returns:
            True если CPL, False если CPA
        """
        # Получаем значения
        a_leads = self._safe_int(campaign_data.get('a_leads', 0))
        r_leads = self._safe_int(campaign_data.get('r_leads', 0))
        revenue = self._safe_float(campaign_data.get('revenue', 0))
        leads = self._safe_int(campaign_data.get('leads', 0))

        # CPL признаки:
        # 1. Есть деньги (revenue > 0)
        # 2. Есть лиды (leads > 0)
        # 3. Апрувнутых лидов нет (a_leads = 0)
        # 4. Отклоненных лидов нет (r_leads = 0)
        # Это означает что платят сразу за лид без системы апрувов
        is_cpl = (
            revenue > 0 and
            leads > 0 and
            a_leads == 0 and
            r_leads == 0
        )

        if is_cpl:
            logger.debug(
                f"Campaign {campaign_data.get('id')} detected as CPL: "
                f"leads={leads}, revenue={revenue}, a_leads={a_leads}, r_leads={r_leads}"
            )
        else:
            logger.debug(
                f"Campaign {campaign_data.get('id')} detected as CPA: "
                f"leads={leads}, revenue={revenue}, a_leads={a_leads}, r_leads={r_leads}"
            )

        return is_cpl

    def detect_with_history(
        self,
        campaign_data: Dict[str, Any],
        historical_stats: List[Dict[str, Any]]
    ) -> bool:
        """
        Определяет тип кампании с учетом исторических данных

        Args:
            campaign_data: текущие данные кампании
            historical_stats: список исторических данных за несколько дней

        Returns:
            True если CPL, False если CPA
        """
        # Сначала проверяем текущие данные
        current_is_cpl = self.detect(campaign_data)

        # Если нет исторических данных, возвращаем текущий результат
        if not historical_stats or len(historical_stats) == 0:
            return current_is_cpl

        # Проверяем историю
        cpl_count = 0
        total_count = 0

        for stats in historical_stats:
            # Пропускаем дни без данных
            revenue = self._safe_float(stats.get('revenue', 0))
            leads = self._safe_int(stats.get('leads', 0))

            if revenue == 0 and leads == 0:
                continue

            total_count += 1

            # Проверяем признаки CPL
            a_leads = self._safe_int(stats.get('a_leads', 0))
            r_leads = self._safe_int(stats.get('r_leads', 0))

            if revenue > 0 and leads > 0 and a_leads == 0 and r_leads == 0:
                cpl_count += 1

        # Если недостаточно данных, используем текущее определение
        if total_count < 3:
            logger.debug("Insufficient historical data, using current detection")
            return current_is_cpl

        # Вычисляем долю CPL дней
        cpl_ratio = cpl_count / total_count

        # Если > 80% дней показывают CPL признаки, это CPL кампания
        is_cpl = cpl_ratio >= self.confidence_threshold

        logger.info(
            f"Campaign {campaign_data.get('id')} historical analysis: "
            f"{cpl_count}/{total_count} days show CPL pattern ({cpl_ratio:.2%})"
        )

        return is_cpl

    def mark_campaign_in_db(
        self,
        binom_id: int,
        is_cpl: bool,
        confidence: Optional[float] = None
    ) -> bool:
        """
        Помечает кампанию в БД как CPL или CPA

        Args:
            binom_id: ID кампании в Binom
            is_cpl: True если CPL, False если CPA
            confidence: уровень уверенности (опционально)

        Returns:
            True если успешно, False при ошибке
        """
        try:
            # Правильное использование генератора get_session()
            for session in get_session():
                # Ищем кампанию
                campaign = session.query(Campaign).filter_by(
                    binom_id=binom_id
                ).first()

                if not campaign:
                    logger.warning(f"Campaign {binom_id} not found in DB")
                    return False

                # Обновляем тип
                old_value = campaign.is_cpl_mode
                campaign.is_cpl_mode = is_cpl

                # Commit происходит автоматически при выходе из контекста

                # Логируем изменение
                if old_value != is_cpl:
                    logger.info(
                        f"Campaign {binom_id} marked as "
                        f"{'CPL' if is_cpl else 'CPA'} "
                        f"(was: {'CPL' if old_value else 'CPA'})"
                        f"{f' with confidence {confidence:.2%}' if confidence else ''}"
                    )

                return True

        except Exception as e:
            logger.error(f"Error marking campaign {binom_id}: {e}")
            return False

    def analyze_all_campaigns(
        self,
        campaigns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Анализирует список кампаний и возвращает статистику

        Args:
            campaigns: список данных кампаний

        Returns:
            Словарь со статистикой
        """
        cpl_campaigns = []
        cpa_campaigns = []

        for campaign in campaigns:
            is_cpl = self.detect(campaign)

            if is_cpl:
                cpl_campaigns.append(campaign)
            else:
                cpa_campaigns.append(campaign)

        # Считаем суммарные метрики
        cpl_revenue = sum(self._safe_float(c.get('revenue', 0)) for c in cpl_campaigns)
        cpa_revenue = sum(self._safe_float(c.get('revenue', 0)) for c in cpa_campaigns)

        total_revenue = cpl_revenue + cpa_revenue

        stats = {
            'total_campaigns': len(campaigns),
            'cpl_campaigns': len(cpl_campaigns),
            'cpa_campaigns': len(cpa_campaigns),
            'cpl_percentage': len(cpl_campaigns) / len(campaigns) * 100 if campaigns else 0,
            'cpl_revenue': cpl_revenue,
            'cpa_revenue': cpa_revenue,
            'total_revenue': total_revenue,
            'cpl_revenue_share': cpl_revenue / total_revenue * 100 if total_revenue > 0 else 0
        }

        logger.info(
            f"Analyzed {len(campaigns)} campaigns: "
            f"{len(cpl_campaigns)} CPL ({stats['cpl_percentage']:.1f}%), "
            f"{len(cpa_campaigns)} CPA"
        )

        return stats

    def _safe_int(self, value: Any, default: int = 0) -> int:
        """Безопасная конвертация в int"""
        try:
            if value == '' or value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Безопасная конвертация в float"""
        try:
            if value == '' or value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default


def detect_campaign_type(campaign_data: Dict[str, Any]) -> str:
    """
    Вспомогательная функция для быстрого определения типа

    Args:
        campaign_data: данные кампании

    Returns:
        'CPL' или 'CPA'
    """
    detector = CPLDetector()
    is_cpl = detector.detect(campaign_data)
    return 'CPL' if is_cpl else 'CPA'
