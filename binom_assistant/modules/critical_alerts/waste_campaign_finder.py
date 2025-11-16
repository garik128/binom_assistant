"""
Модуль поиска кампаний стабильно сливающих бюджет
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager

from storage.database.base import get_session
from storage.database.models import Campaign, CampaignStatsDaily
from ..base_module import BaseModule, ModuleMetadata, ModuleConfig


@contextmanager
def get_db_session():
    """
    Локальная обертка над get_session() для использования в with.
    Преобразует генератор в контекстный менеджер.
    """
    session_gen = get_session()
    session = next(session_gen)
    try:
        yield session
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


class WasteCampaignFinder(BaseModule):
    """
    Детектор кампаний со стабильным сливом бюджета.

    Находит кампании с устойчиво отрицательным ROI на протяжении нескольких дней подряд.
    Помогает остановить хронические "пожиратели бюджета".

    Критерии:
    - ROI < -50% (настраивается) более N дней подряд (настраивается)
    - Отсутствие положительной динамики
    - Минимальный расход > $1/день (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="waste_campaign_finder",
            name="Слив бюджета",
            category="critical_alerts",
            description="Стабильно убыточные кампании без улучшений",
            detailed_description="Выявляет кампании с устойчиво отрицательным ROI на протяжении нескольких дней. Помогает остановить хронические 'пожиратели бюджета'.",
            version="1.0.1",  # Обновлена версия - исправлена логика фильтрации
            author="Binom Assistant",
            priority="critical",
            tags=["roi", "waste", "critical", "chronic"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Критический модуль - автозапуск выключен по умолчанию
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=30,
            cache_ttl_seconds=3600,
            params={
                "roi_threshold": -50,  # ROI меньше -50%
                "min_daily_spend": 1,  # минимум $1/день
                "consecutive_days": 7,  # количество дней подряд
                "analysis_period": 14,  # период анализа в днях
                "recovery_threshold": -30,  # порог ROI для определения восстановления
                "severity_critical": 1.5,  # множитель consecutive_days для critical severity
                "severity_high": 1.0  # множитель consecutive_days для high severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.

        Returns:
            Dict с описаниями параметров в формате:
            {
                "param_name": {
                    "label": "Человеческое название",
                    "description": "Подробное описание",
                    "type": "number" | "string" | "boolean",
                    "min": минимальное значение (для number),
                    "max": максимальное значение (для number),
                    "step": шаг изменения (для number)
                }
            }
        """
        return {
            "roi_threshold": {
                "label": "Порог ROI",
                "description": "ROI ниже которого день считается убыточным (в процентах)",
                "type": "number",
                "min": -100,
                "max": 0,
                "step": 5
            },
            "min_daily_spend": {
                "label": "Минимальный дневной расход",
                "description": "Минимальный средний расход в день для анализа (в долларах)",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "step": 0.5
            },
            "consecutive_days": {
                "label": "Минимум дней подряд",
                "description": "Сколько дней подряд должен быть плохой ROI для срабатывания",
                "type": "number",
                "min": 3,
                "max": 365,
                "step": 1
            },
            "analysis_period": {
                "label": "Период анализа",
                "description": "Количество последних дней для анализа",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "recovery_threshold": {
                "label": "Порог восстановления (ROI %)",
                "description": "Средний ROI последних 3 дней выше этого значения считается восстановлением",
                "type": "number",
                "min": -100,
                "max": 0,
                "step": 5
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "consecutive_days_multiplier",
            "metric_label": "Множитель дней подряд",
            "metric_unit": "x",
            "description": "Пороги критичности на основе длительности стабильного слива (кратность от минимального количества дней)",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичный множитель",
                    "description": "Множитель минимального количества дней для критичного уровня (например, 1.5x от 7 дней = 10.5 дней)",
                    "type": "number",
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.1,
                    "default": 1.5
                },
                "severity_high": {
                    "label": "Высокий множитель",
                    "description": "Множитель минимального количества дней для высокого уровня (обычно 1.0 = точно минимум дней)",
                    "type": "number",
                    "min": 0.8,
                    "max": 2.0,
                    "step": 0.1,
                    "default": 1.0
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "Дней подряд >= critical * min_days"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical * min_days > Дней подряд >= high * min_days"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "Дней подряд < high * min_days"}
            ]
        }

    def _check_consecutive_negative_days(
        self,
        daily_stats: List[tuple],
        roi_threshold: float,
        min_consecutive: int
    ) -> tuple:
        """
        Проверяет наличие последовательных дней с отрицательным ROI.

        Args:
            daily_stats: Список кортежей (date, cost, revenue, clicks, leads)
            roi_threshold: Пороговое значение ROI
            min_consecutive: Минимальное количество дней подряд

        Returns:
            (bool, int, float): (найдены ли, макс последовательность, средний ROI за плохие дни)
        """
        if not daily_stats:
            return False, 0, 0

        current_streak = 0
        max_streak = 0
        bad_days_roi = []

        # Сортируем по дате
        sorted_stats = sorted(daily_stats, key=lambda x: x[0])

        for row in sorted_stats:
            date, cost, revenue = row[0], row[1], row[2]
            if cost > 0:
                roi = ((revenue - cost) / cost) * 100
                if roi < roi_threshold:
                    current_streak += 1
                    bad_days_roi.append(roi)
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0

        avg_bad_roi = sum(bad_days_roi) / len(bad_days_roi) if bad_days_roi else 0
        return max_streak >= min_consecutive, max_streak, avg_bad_roi

    def _check_no_recovery(self, daily_stats: List[tuple], recovery_threshold: float) -> bool:
        """
        Проверяет отсутствие признаков восстановления.

        Args:
            daily_stats: Список кортежей (date, cost, revenue, clicks, leads)
            recovery_threshold: Порог ROI для определения восстановления

        Returns:
            bool: True если нет признаков восстановления
        """
        if len(daily_stats) < 3:
            return True

        # Берем последние 3 дня и сравниваем с предыдущими
        sorted_stats = sorted(daily_stats, key=lambda x: x[0])
        last_3_days = sorted_stats[-3:]

        # Вычисляем средний ROI последних 3 дней
        last_roi_sum = 0
        last_roi_count = 0

        for row in last_3_days:
            date, cost, revenue = row[0], row[1], row[2]
            if cost > 0:
                roi = ((revenue - cost) / cost) * 100
                last_roi_sum += roi
                last_roi_count += 1

        if last_roi_count == 0:
            return True

        avg_last_roi = last_roi_sum / last_roi_count

        # Если средний ROI последних дней выше порога, считаем что есть восстановление
        return avg_last_roi < recovery_threshold

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ кампаний со стабильным сливом бюджета через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях со стабильным сливом
        """
        # Получение параметров
        roi_threshold = config.params.get("roi_threshold", -50)
        min_daily_spend = config.params.get("min_daily_spend", 1)
        consecutive_days = config.params.get("consecutive_days", 7)
        analysis_period = config.params.get("analysis_period", 14)
        recovery_threshold = config.params.get("recovery_threshold", -30)

        # Получение настраиваемых порогов severity
        severity_critical_multiplier = config.params.get("severity_critical", 1.5)
        severity_high_multiplier = config.params.get("severity_high", 1.0)

        date_from = datetime.now().date() - timedelta(days=analysis_period - 1)

        # Работа с БД
        with get_db_session() as session:
            # Сначала получаем список всех кампаний с достаточным расходом
            campaigns_query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost > 0
            ).group_by(
                Campaign.internal_id
            ).having(
                func.avg(CampaignStatsDaily.cost) >= min_daily_spend
            )

            campaigns = campaigns_query.all()

            # Для каждой кампании получаем дневные данные
            waste_campaigns = []
            total_wasted = 0

            for campaign in campaigns:
                # Получаем дневную статистику
                daily_query = session.query(
                    CampaignStatsDaily.date,
                    CampaignStatsDaily.cost,
                    CampaignStatsDaily.revenue,
                    CampaignStatsDaily.clicks,
                    CampaignStatsDaily.leads
                ).filter(
                    CampaignStatsDaily.campaign_id == campaign.internal_id,
                    CampaignStatsDaily.date >= date_from,
                    CampaignStatsDaily.cost > 0
                ).order_by(
                    CampaignStatsDaily.date
                )

                daily_stats = daily_query.all()

                if not daily_stats:
                    continue

                # Проверяем наличие последовательных дней с плохим ROI
                has_streak, max_streak, avg_bad_roi = self._check_consecutive_negative_days(
                    daily_stats,
                    roi_threshold,
                    consecutive_days
                )

                if not has_streak:
                    continue

                # Вычисляем общие метрики за период
                total_cost = sum(float(s.cost) for s in daily_stats)
                total_revenue = sum(float(s.revenue) for s in daily_stats)
                total_clicks = sum(int(s.clicks) for s in daily_stats)
                total_leads = sum(int(s.leads) for s in daily_stats)

                # Вычисляем общий ROI
                if total_cost > 0:
                    overall_roi = ((total_revenue - total_cost) / total_cost) * 100
                else:
                    overall_roi = 0

                # Проверяем отсутствие восстановления
                # ВАЖНО: Проверяем только если серия не прервана, НЕ общий ROI
                if not self._check_no_recovery(daily_stats, recovery_threshold):
                    continue

                loss = total_cost - total_revenue
                total_wasted += loss

                # Определение критичности
                if max_streak >= consecutive_days * severity_critical_multiplier:
                    severity = "critical"
                elif max_streak >= consecutive_days * severity_high_multiplier:
                    severity = "high"
                else:
                    severity = "medium"

                waste_campaigns.append({
                    "campaign_id": campaign.internal_id,
                    "binom_id": campaign.binom_id,
                    "name": campaign.current_name,
                    "group": campaign.group_name or "Без группы",
                    "total_cost": total_cost,
                    "total_revenue": total_revenue,
                    "avg_roi": round(overall_roi, 2),
                    "avg_bad_roi": round(avg_bad_roi, 2),
                    "loss": round(loss, 2),
                    "consecutive_bad_days": max_streak,
                    "severity": severity,
                    "total_clicks": total_clicks,
                    "total_leads": total_leads
                })

            # Сортировка по убыткам
            waste_campaigns.sort(key=lambda x: x['loss'], reverse=True)

            return {
                "campaigns": waste_campaigns,
                "summary": {
                    "total_found": len(waste_campaigns),
                    "total_wasted": round(total_wasted, 2),
                    "critical_count": sum(1 for c in waste_campaigns if c['severity'] == 'critical'),
                    "high_count": sum(1 for c in waste_campaigns if c['severity'] == 'high'),
                    "medium_count": sum(1 for c in waste_campaigns if c['severity'] == 'medium'),
                    "avg_bad_streak": round(sum(c['consecutive_bad_days'] for c in waste_campaigns) / len(waste_campaigns), 1) if waste_campaigns else 0
                },
                "period_days": analysis_period,
                "thresholds": {
                    "roi": roi_threshold,
                    "min_daily_spend": min_daily_spend,
                    "consecutive_days": consecutive_days,
                    "recovery_threshold": recovery_threshold,
                    "severity_critical": severity_critical_multiplier,
                    "severity_high": severity_high_multiplier
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        Вся информация теперь в алертах.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        campaigns = raw_data["campaigns"][:10]  # Топ-10

        if not campaigns:
            return []

        return [
            {
                "id": "consecutive_days_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in campaigns],
                    "datasets": [{
                        "label": "Дней подряд с убытком",
                        "data": [c["consecutive_bad_days"] for c in campaigns],
                        "backgroundColor": "rgba(255, 99, 132, 0.5)",
                        "borderColor": "rgba(255, 99, 132, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Длительность слива бюджета (дней подряд)"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True
                        }
                    }
                }
            },
            {
                "id": "waste_distribution_chart",
                "type": "pie",
                "data": {
                    "labels": [c["name"][:25] for c in campaigns[:5]],
                    "datasets": [{
                        "data": [c["loss"] for c in campaigns[:5]],
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.8)",
                            "rgba(255, 159, 64, 0.8)",
                            "rgba(255, 205, 86, 0.8)",
                            "rgba(75, 192, 192, 0.8)",
                            "rgba(54, 162, 235, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение потерь (Топ-5)"
                        }
                    }
                }
            }
        ]

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов.
        Возвращает один общий алерт с краткой сводкой вместо множества алертов.
        """
        summary = raw_data["summary"]
        campaigns = raw_data["campaigns"]
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        # Если есть кампании со стабильным сливом, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            total_wasted = summary["total_wasted"]
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]
            avg_bad_streak = summary["avg_bad_streak"]

            # Получаем пороги для сообщения
            severity_critical_multiplier = thresholds.get("severity_critical", 1.5)
            consecutive_days = thresholds.get("consecutive_days", 7)
            critical_days_threshold = int(consecutive_days * severity_critical_multiplier)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: {total_found} кампаний стабильно сливают бюджет, потери: ${total_wasted:.2f}"
                if critical_count > 1:
                    message += f" (из них {critical_count} критических с >{critical_days_threshold} дней подряд)"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: {total_found} кампаний стабильно сливают бюджет, потери: ${total_wasted:.2f}"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} кампаний стабильно сливают бюджет, потери: ${total_wasted:.2f}"

            message += f"\nСредняя длительность слива: {avg_bad_streak:.1f} дней"

            # Добавляем краткую информацию о топ-3
            top_3 = campaigns[:3]
            if top_3:
                message += "\n\nТоп-3 по потерям:"
                for i, campaign in enumerate(top_3, 1):
                    message += f"\n{i}. {campaign['name']}: {campaign['consecutive_bad_days']} дней подряд, потери ${campaign['loss']:.2f}"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Срочно остановите критические кампании. Они стабильно сливают бюджет без признаков восстановления"
            else:
                recommended_action = "Проанализируйте кампании и рассмотрите их остановку или радикальное изменение настроек"

            alerts.append({
                "type": "waste_campaigns_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "campaigns_count": total_found,
                "total_wasted": total_wasted,
                "critical_count": critical_count,
                "avg_bad_streak": avg_bad_streak
            })

        return alerts
