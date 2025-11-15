"""
Модуль прогнозирования revenue на 7 дней вперед
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
import numpy as np
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


class RevenueProjection(BaseModule):
    """
    Прогнозирование revenue на следующие 7 дней.

    Использует исторические данные за последние 14-30 дней для прогноза revenue.
    Применяет простую линейную экстраполяцию с учетом тренда.

    Критерии:
    - Минимум 7 дней истории
    - Минимум $10 общего revenue за период
    - Прогноз на 7 дней вперед (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="revenue_projection",
            name="Прогноз дохода",
            category="predictive",
            description="Прогнозирует revenue на следующие 7 дней на основе исторических данных",
            detailed_description="Модуль анализирует динамику revenue за последние 14-30 дней и строит прогноз используя линейную экстраполяцию с учетом тренда.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["revenue", "forecast", "prediction", "income"]
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
                "history_days": 14,  # дней истории для анализа
                "forecast_days": 7,  # дней для прогноза
                "min_revenue": 10,  # минимум $10 общего revenue за период
                "confidence_level": 80  # уровень доверительного интервала (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "history_days": {
                "label": "Дней истории",
                "description": "Количество дней истории для анализа",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "forecast_days": {
                "label": "Дней прогноза",
                "description": "На сколько дней вперед строить прогноз",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "min_revenue": {
                "label": "Минимальный revenue",
                "description": "Минимальный общий revenue за период ($)",
                "type": "number",
                "min": 1,
                "max": 1000,
                "default": 10
            },
            "confidence_level": {
                "label": "Уровень доверия",
                "description": "Уровень доверительного интервала (%)",
                "type": "number",
                "min": 50,
                "max": 99,
                "default": 80
            }
        }

    def _simple_linear_regression(self, x_values: List[float], y_values: List[float]) -> tuple:
        """
        Простая линейная регрессия.

        Returns:
            (slope, intercept, r_squared)
        """
        n = len(x_values)
        if n < 2:
            return 0, 0, 0

        x_mean = np.mean(x_values)
        y_mean = np.mean(y_values)

        numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0, y_mean, 0

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # R-squared
        ss_tot = sum((y_values[i] - y_mean) ** 2 for i in range(n))
        ss_res = sum((y_values[i] - (slope * x_values[i] + intercept)) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return slope, intercept, r_squared

    def _calculate_forecast(self, historical_revenue: List[float], forecast_days: int, confidence_level: int) -> Dict[str, Any]:
        """
        Рассчитывает прогноз revenue используя линейную регрессию.

        Args:
            historical_revenue: Список исторических значений revenue
            forecast_days: Количество дней для прогноза
            confidence_level: Уровень доверительного интервала (не используется)

        Returns:
            Dict с прогнозными значениями
        """
        # Минимум 7 дней для значимого прогноза
        if len(historical_revenue) < 7:
            return None

        # Подготовка данных для регрессии
        x_values = list(range(len(historical_revenue)))
        y_values = historical_revenue

        # Линейная регрессия
        slope, intercept, r_squared = self._simple_linear_regression(x_values, y_values)

        # Расчет стандартного отклонения для информации
        std_dev = np.std(historical_revenue)

        # Прогноз
        forecast_values = []
        total_projected_revenue = 0

        for i in range(forecast_days):
            day_offset = len(historical_revenue) + i
            predicted_revenue = slope * day_offset + intercept

            # Revenue не может быть отрицательным
            predicted_revenue = max(0, predicted_revenue)

            forecast_values.append({
                "day": i + 1,
                "predicted_revenue": round(predicted_revenue, 2)
            })

            total_projected_revenue += predicted_revenue

        return {
            "forecast": forecast_values,
            "total_projected_revenue": round(total_projected_revenue, 2),
            "trend_slope": round(slope, 4),
            "r_squared": round(r_squared, 4),
            "avg_historical_revenue": round(np.mean(historical_revenue), 2),
            "std_dev": round(std_dev, 2)
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Прогнозирование revenue для активных кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Прогнозы revenue для кампаний
        """
        # Получение параметров
        history_days = config.params.get("history_days", 14)
        forecast_days = config.params.get("forecast_days", 7)
        min_revenue = config.params.get("min_revenue", 10)
        confidence_level = config.params.get("confidence_level", 80)

        date_from = datetime.now().date() - timedelta(days=history_days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все активные кампании с историей
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.leads
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.revenue > 0
            ).order_by(
                Campaign.internal_id,
                CampaignStatsDaily.date
            )

            results = query.all()

            # Группировка по кампаниям
            campaigns_data = defaultdict(lambda: {
                "binom_id": None,
                "name": None,
                "group": None,
                "daily_stats": []
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                revenue = float(row.revenue)

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": float(row.cost),
                    "revenue": revenue,
                    "clicks": row.clicks,
                    "leads": row.leads
                })

            # Обработка и прогнозирование
            forecasts = []
            total_campaigns_analyzed = 0
            increasing_forecasts = 0
            decreasing_forecasts = 0
            stable_forecasts = 0

            for campaign_id, data in campaigns_data.items():
                daily_stats = data["daily_stats"]

                # Фильтрация: минимальный revenue за весь период
                total_revenue = sum(d["revenue"] for d in daily_stats)
                if total_revenue < min_revenue:
                    continue

                # Извлекаем revenue для прогноза
                historical_revenue = [d["revenue"] for d in daily_stats]

                # Рассчитываем прогноз
                forecast_result = self._calculate_forecast(
                    historical_revenue,
                    forecast_days,
                    confidence_level
                )

                if not forecast_result:
                    continue

                # Агрегированная статистика
                total_cost = sum(d["cost"] for d in daily_stats)
                avg_daily_revenue = total_revenue / len(daily_stats)
                current_daily_revenue = historical_revenue[-1]

                # Средний прогнозируемый дневной revenue
                predicted_daily_revenue = forecast_result["total_projected_revenue"] / forecast_days

                # Классификация тренда ($/день)
                trend_slope = forecast_result["trend_slope"]
                if trend_slope > 1:
                    trend = "increasing"
                    trend_label = "Рост"
                    increasing_forecasts += 1
                elif trend_slope < -1:
                    trend = "decreasing"
                    trend_label = "Падение"
                    decreasing_forecasts += 1
                else:
                    trend = "stable"
                    trend_label = "Стабильный"
                    stable_forecasts += 1

                forecasts.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "current_daily_revenue": round(current_daily_revenue, 2),
                    "predicted_daily_revenue": round(predicted_daily_revenue, 2),
                    "total_projected_revenue": forecast_result["total_projected_revenue"],
                    "forecast": forecast_result["forecast"],
                    "trend": trend,
                    "trend_label": trend_label,
                    "trend_slope": forecast_result["trend_slope"],
                    "r_squared": forecast_result["r_squared"],
                    "avg_historical_revenue": forecast_result["avg_historical_revenue"],
                    "std_dev": forecast_result["std_dev"],
                    "days_of_data": len(daily_stats)
                })

                total_campaigns_analyzed += 1

            # Сортировка: по убыванию total_projected_revenue - сначала самые доходные
            forecasts.sort(key=lambda x: x["total_projected_revenue"], reverse=True)

            return {
                "forecasts": forecasts,
                "summary": {
                    "total_analyzed": total_campaigns_analyzed,
                    "increasing_count": increasing_forecasts,
                    "decreasing_count": decreasing_forecasts,
                    "stable_count": stable_forecasts,
                    "avg_r_squared": round(np.mean([f["r_squared"] for f in forecasts]), 3) if forecasts else 0,
                    "total_projected_revenue": round(sum(f["total_projected_revenue"] for f in forecasts), 2)
                },
                "period": {
                    "history_days": history_days,
                    "forecast_days": forecast_days,
                    "date_from": date_from.isoformat(),
                    "date_to": (datetime.now().date() + timedelta(days=forecast_days)).isoformat()
                },
                "params": {
                    "min_revenue": min_revenue,
                    "confidence_level": confidence_level
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        forecasts = raw_data.get("forecasts", [])[:5]  # Топ-5

        if not forecasts:
            return []

        charts = []

        # График прогнозов для топ-5 кампаний по revenue
        for idx, forecast_data in enumerate(forecasts):
            forecast_points = forecast_data["forecast"]

            charts.append({
                "id": f"revenue_forecast_chart_{idx}",
                "type": "line",
                "data": {
                    "labels": [f"День {f['day']}" for f in forecast_points],
                    "datasets": [
                        {
                            "label": "Прогноз Revenue ($)",
                            "data": [f["predicted_revenue"] for f in forecast_points],
                            "borderColor": "rgba(75, 192, 192, 1)",
                            "backgroundColor": "rgba(75, 192, 192, 0.2)",
                            "fill": False,
                            "tension": 0.1
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": f"Прогноз: {forecast_data['name'][:40]}"
                        }
                    },
                    "scales": {
                        "y": {
                            "title": {
                                "display": True,
                                "text": "Revenue ($)"
                            }
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для прогнозов с сильным падением revenue.
        """
        forecasts = raw_data.get("forecasts", [])
        alerts = []

        # Находим кампании с прогнозом падения
        decreasing = [f for f in forecasts if f["trend"] == "decreasing"]

        if decreasing:
            # Берем топ-3 с самым сильным падением
            top_decreasing = sorted(decreasing, key=lambda x: x["trend_slope"])[:3]

            message = f"Прогноз показывает падение revenue для {len(decreasing)} кампаний\n\n"
            message += "Топ-3 с наибольшим падением:\n"

            for i, campaign in enumerate(top_decreasing, 1):
                message += f"{i}. {campaign['name']}: "
                message += f"текущий ${campaign['current_daily_revenue']:.2f}/день -> "
                message += f"прогноз ${campaign['predicted_daily_revenue']:.2f}/день "
                message += f"(тренд: ${campaign['trend_slope']:.2f}/день)\n"

            alerts.append({
                "type": "revenue_projection_decreasing",
                "severity": "high" if len(decreasing) > 5 else "medium",
                "message": message,
                "recommended_action": "Проанализируйте причины падения дохода и рассмотрите корректировку стратегии",
                "campaigns_count": len(decreasing),
                "avg_decline": round(np.mean([c["trend_slope"] for c in decreasing]), 2)
            })

        return alerts
