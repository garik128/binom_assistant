"""
Модуль отслеживания общей динамики портфеля (Total Performance Tracker)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict

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


class TotalPerformanceTracker(BaseModule):
    """
    Модуль отслеживания общей динамики портфеля (Total Performance Tracker).

    Отслеживает динамику общих показателей:
    - Агрегированные метрики: общий ROI, расход, прибыль
    - Сравнение периодов (текущий vs предыдущий)
    - Тренд изменения метрик
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="total_performance_tracker",
            name="Общая динамика",
            category="portfolio",
            description="Отслеживает динамику общих показателей портфеля",
            detailed_description="Модуль анализирует общие показатели портфеля за выбранный период и сравнивает их с предыдущим периодом. Показывает тренд изменения ключевых метрик: ROI, расход, прибыль, клики, лиды. Помогает быстро оценить общую динамику портфеля. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="high",
            tags=["portfolio", "performance", "dynamics", "trends", "roi", "metrics"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Некритический модуль - не запускать автоматически
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=60,
            cache_ttl_seconds=3600,
            params={
                "days": 7,  # период для анализа
                "min_change_threshold": 2.0,  # минимальное изменение для уведомлений (%)
                "high_roi_threshold": 20,  # порог высокого ROI (%)
                "high_cost_change_threshold": 20  # порог значительного изменения расходов (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа портфеля",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_change_threshold": {
                "label": "Порог изменения (%)",
                "description": "Минимальное изменение метрики для генерации уведомления",
                "type": "number",
                "min": 0.1,
                "max": 50,
                "default": 2.0
            },
            "high_roi_threshold": {
                "label": "Порог высокого ROI (%)",
                "description": "Порог для определения высокого ROI",
                "type": "number",
                "min": 0,
                "max": 200,
                "default": 20
            },
            "high_cost_change_threshold": {
                "label": "Порог изменения расходов (%)",
                "description": "Порог значительного изменения расходов",
                "type": "number",
                "min": 5,
                "max": 10000,
                "default": 20
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ общей динамики портфеля.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о динамике портфеля
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_change_threshold = config.params.get("min_change_threshold", 2.0)
        high_roi_threshold = config.params.get("high_roi_threshold", 20)
        high_cost_change_threshold = config.params.get("high_cost_change_threshold", 20)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)
        date_to = datetime.now().date()

        # Предыдущий период (для сравнения)
        prev_date_from = date_from - timedelta(days=days)
        prev_date_to = date_from - timedelta(days=1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем данные за текущий период
            current_data = self._aggregate_period_data(
                session, date_from, date_to
            )

            # Получаем данные за предыдущий период
            previous_data = self._aggregate_period_data(
                session, prev_date_from, prev_date_to
            )

            # Расчет изменений
            changes = self._calculate_changes(current_data, previous_data)

            # Определение тренда
            trend = self._determine_trend(changes, min_change_threshold)

            # Формируем summary для отображения в карточке модуля
            summary = {
                "total_cost": current_data.get("total_cost", 0),
                "total_revenue": current_data.get("total_revenue", 0),
                "total_profit": current_data.get("total_profit", 0),
                "roi": current_data.get("total_roi", 0),
                "clicks": current_data.get("total_clicks", 0),
                "leads": current_data.get("total_leads", 0),
                "approved_leads": current_data.get("total_a_leads", 0),
                "trend": trend
            }

            return {
                "summary": summary,
                "current_period": current_data,
                "previous_period": previous_data,
                "changes": changes,
                "trend": trend,
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat()
                }
            }

    def _aggregate_period_data(self, session, date_from, date_to) -> Dict[str, Any]:
        """
        Агрегирует данные за период.

        Args:
            session: Сессия БД
            date_from: Начальная дата
            date_to: Конечная дата

        Returns:
            Dict[str, Any]: Агрегированные данные за период
        """
        query = session.query(
            func.sum(CampaignStatsDaily.cost).label('total_cost'),
            func.sum(CampaignStatsDaily.revenue).label('total_revenue'),
            func.sum(CampaignStatsDaily.leads).label('total_leads'),
            func.sum(CampaignStatsDaily.a_leads).label('total_a_leads'),
            func.sum(CampaignStatsDaily.clicks).label('total_clicks')
        ).filter(
            CampaignStatsDaily.date >= date_from,
            CampaignStatsDaily.date <= date_to
        )

        result = query.first()

        # Обработка None значений
        total_cost = float(result.total_cost or 0)
        total_revenue = float(result.total_revenue or 0)
        total_leads = float(result.total_leads or 0)
        total_a_leads = float(result.total_a_leads or 0)
        total_clicks = float(result.total_clicks or 0)

        # Расчет ROI
        total_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

        return {
            "total_cost": round(total_cost, 2),
            "total_revenue": round(total_revenue, 2),
            "total_profit": round(total_revenue - total_cost, 2),
            "total_roi": round(total_roi, 1),
            "total_clicks": int(total_clicks),
            "total_leads": int(total_leads),
            "total_a_leads": int(total_a_leads)
        }

    def _calculate_changes(self, current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, float]:
        """
        Рассчитывает процентные изменения между периодами.

        Args:
            current: Текущие данные
            previous: Предыдущие данные

        Returns:
            Dict[str, float]: Процентные изменения
        """
        changes = {}

        # Изменение расхода
        if previous['total_cost'] > 0:
            changes['cost_change'] = round(
                ((current['total_cost'] - previous['total_cost']) / previous['total_cost']) * 100,
                1
            )
        else:
            changes['cost_change'] = 0 if current['total_cost'] == 0 else 100

        # Изменение дохода
        if previous['total_revenue'] > 0:
            changes['revenue_change'] = round(
                ((current['total_revenue'] - previous['total_revenue']) / previous['total_revenue']) * 100,
                1
            )
        else:
            changes['revenue_change'] = 0 if current['total_revenue'] == 0 else 100

        # Изменение прибыли
        if previous['total_profit'] > 0:
            changes['profit_change'] = round(
                ((current['total_profit'] - previous['total_profit']) / previous['total_profit']) * 100,
                1
            )
        elif previous['total_profit'] == 0 and current['total_profit'] > 0:
            changes['profit_change'] = 100
        elif previous['total_profit'] == 0 and current['total_profit'] == 0:
            changes['profit_change'] = 0
        else:
            changes['profit_change'] = -100

        # Изменение ROI
        if previous['total_roi'] != 0:
            changes['roi_change'] = round(
                current['total_roi'] - previous['total_roi'],
                1
            )
        else:
            changes['roi_change'] = current['total_roi'] - 0

        # Изменение кликов
        if previous['total_clicks'] > 0:
            changes['clicks_change'] = round(
                ((current['total_clicks'] - previous['total_clicks']) / previous['total_clicks']) * 100,
                1
            )
        else:
            changes['clicks_change'] = 0 if current['total_clicks'] == 0 else 100

        # Изменение лидов
        if previous['total_leads'] > 0:
            changes['leads_change'] = round(
                ((current['total_leads'] - previous['total_leads']) / previous['total_leads']) * 100,
                1
            )
        else:
            changes['leads_change'] = 0 if current['total_leads'] == 0 else 100

        # Изменение одобренных лидов
        if previous['total_a_leads'] > 0:
            changes['a_leads_change'] = round(
                ((current['total_a_leads'] - previous['total_a_leads']) / previous['total_a_leads']) * 100,
                1
            )
        else:
            changes['a_leads_change'] = 0 if current['total_a_leads'] == 0 else 100

        return changes

    def _determine_trend(self, changes: Dict[str, float], threshold: float = 2.0) -> str:
        """
        Определяет общий тренд на основе изменений.

        Args:
            changes: Словарь с процентными изменениями
            threshold: Пороговое значение для определения значимых изменений (%)

        Returns:
            str: Тренд ("improving", "stable", "declining")
        """
        # Ключевые метрики для определения тренда
        revenue_change = changes.get('revenue_change', 0)
        roi_change = changes.get('roi_change', 0)
        profit_change = changes.get('profit_change', 0)

        # Подсчитываем положительные и отрицательные изменения
        positive_count = 0
        negative_count = 0

        if revenue_change > threshold:
            positive_count += 1
        elif revenue_change < -threshold:
            negative_count += 1

        if roi_change > threshold:
            positive_count += 1
        elif roi_change < -threshold:
            negative_count += 1

        if profit_change > threshold:
            positive_count += 1
        elif profit_change < -threshold:
            negative_count += 1

        # Определяем тренд
        if positive_count > negative_count:
            return "improving"
        elif negative_count > positive_count:
            return "declining"
        else:
            return "stable"

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО для этого модуля.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        current = raw_data.get("current_period", {})
        previous = raw_data.get("previous_period", {})
        changes = raw_data.get("changes", {})

        charts = []

        # График сравнения ключевых метрик
        charts.append({
            "id": "total_performance_comparison",
            "type": "bar",
            "data": {
                "labels": ["Текущий период", "Предыдущий период"],
                "datasets": [
                    {
                        "label": "Расход ($)",
                        "data": [
                            current.get('total_cost', 0),
                            previous.get('total_cost', 0)
                        ],
                        "backgroundColor": "rgba(255, 159, 64, 0.7)"
                    },
                    {
                        "label": "Доход ($)",
                        "data": [
                            current.get('total_revenue', 0),
                            previous.get('total_revenue', 0)
                        ],
                        "backgroundColor": "rgba(75, 192, 75, 0.7)"
                    },
                    {
                        "label": "Прибыль ($)",
                        "data": [
                            current.get('total_profit', 0),
                            previous.get('total_profit', 0)
                        ],
                        "backgroundColor": "rgba(54, 162, 235, 0.7)"
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Сравнение периодов"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True
                    }
                }
            }
        })

        # График изменений в процентах
        roi_color = "rgba(40, 167, 69, 0.7)" if changes.get('roi_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)"
        revenue_color = "rgba(40, 167, 69, 0.7)" if changes.get('revenue_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)"
        profit_color = "rgba(40, 167, 69, 0.7)" if changes.get('profit_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)"

        charts.append({
            "id": "total_performance_changes",
            "type": "bar",
            "data": {
                "labels": ["Расход", "Доход", "Прибыль", "ROI", "Клики", "Лиды"],
                "datasets": [{
                    "label": "Изменение (%)",
                    "data": [
                        changes.get('cost_change', 0),
                        changes.get('revenue_change', 0),
                        changes.get('profit_change', 0),
                        changes.get('roi_change', 0),
                        changes.get('clicks_change', 0),
                        changes.get('leads_change', 0)
                    ],
                    "backgroundColor": [
                        "rgba(255, 159, 64, 0.7)",  # cost
                        "rgba(40, 167, 69, 0.7)" if changes.get('revenue_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)",
                        "rgba(40, 167, 69, 0.7)" if changes.get('profit_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)",
                        "rgba(40, 167, 69, 0.7)" if changes.get('roi_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)",
                        "rgba(40, 167, 69, 0.7)" if changes.get('clicks_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)",
                        "rgba(40, 167, 69, 0.7)" if changes.get('leads_change', 0) >= 0 else "rgba(220, 53, 69, 0.7)"
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Изменение метрик vs предыдущий период"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "y": {
                        "title": {
                            "display": True,
                            "text": "Процентное изменение (%)"
                        }
                    }
                }
            }
        })

        # График ROI за периоды
        charts.append({
            "id": "total_performance_roi",
            "type": "line",
            "data": {
                "labels": ["Предыдущий период", "Текущий период"],
                "datasets": [{
                    "label": "ROI (%)",
                    "data": [
                        previous.get('total_roi', 0),
                        current.get('total_roi', 0)
                    ],
                    "borderColor": "rgba(13, 110, 253, 1)",
                    "backgroundColor": "rgba(13, 110, 253, 0.1)",
                    "borderWidth": 2,
                    "pointBackgroundColor": "rgba(13, 110, 253, 1)",
                    "pointBorderColor": "#fff",
                    "pointBorderWidth": 2,
                    "tension": 0.4
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Динамика ROI"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "y": {
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для портфеля.
        """
        current = raw_data.get("current_period", {})
        previous = raw_data.get("previous_period", {})
        changes = raw_data.get("changes", {})
        trend = raw_data.get("trend", "stable")

        alerts = []

        # Алерт о тренде
        trend_message = {
            "improving": "Портфель улучшается! Все ключевые метрики растут.",
            "stable": "Портфель стабилен. Метрики остаются на прежнем уровне.",
            "declining": "Внимание! Портфель ухудшается. Требуется анализ причин."
        }.get(trend, "Неизвестный тренд")

        severity = {
            "improving": "info",
            "stable": "info",
            "declining": "warning"
        }.get(trend, "info")

        alerts.append({
            "type": "performance_trend",
            "severity": severity,
            "message": trend_message,
            "trend": trend
        })

        # Алерт о ROI
        roi_current = current.get('total_roi', 0)
        roi_change = changes.get('roi_change', 0)

        if roi_current > 50:
            roi_message = f"Отличный ROI: {roi_current}% (+{roi_change}%)"
            roi_severity = "info"
        elif roi_current > 20:
            roi_message = f"Хороший ROI: {roi_current}% ({roi_change:+.1f}%)"
            roi_severity = "info"
        elif roi_current > 0:
            roi_message = f"ROI положительный: {roi_current}% ({roi_change:+.1f}%)"
            roi_severity = "warning"
        else:
            roi_message = f"ROI отрицательный: {roi_current}% ({roi_change:+.1f}%)"
            roi_severity = "critical"

        alerts.append({
            "type": "performance_roi",
            "severity": roi_severity,
            "message": roi_message,
            "roi": roi_current,
            "roi_change": roi_change
        })

        # Алерт о расходах
        cost_change = changes.get('cost_change', 0)
        if cost_change > 20:
            cost_message = f"Резкий рост расходов: +{cost_change}%. Убедитесь, что бюджет контролируется."
            cost_severity = "warning"
        elif cost_change < -20:
            cost_message = f"Значительное снижение расходов: {cost_change}%. Проверьте, не заблокированы ли кампании."
            cost_severity = "info"
        else:
            cost_message = f"Расходы изменились на {cost_change:+.1f}%"
            cost_severity = "info"

        alerts.append({
            "type": "performance_cost",
            "severity": cost_severity,
            "message": cost_message,
            "cost_change": cost_change
        })

        # Алерт о прибыли
        profit_current = current.get('total_profit', 0)
        profit_change = changes.get('profit_change', 0)

        if profit_current > 0:
            profit_status = f"Положительная прибыль: ${profit_current:.2f}"
            if profit_change > 0:
                profit_status += f" (+{profit_change}%)"
            else:
                profit_status += f" ({profit_change}%)"
            profit_severity = "info"
        else:
            profit_status = f"Отрицательная прибыль: ${profit_current:.2f} ({profit_change:+.1f}%)"
            profit_severity = "critical"

        alerts.append({
            "type": "performance_profit",
            "severity": profit_severity,
            "message": profit_status,
            "profit": profit_current,
            "profit_change": profit_change
        })

        return alerts
