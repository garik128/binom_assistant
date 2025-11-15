"""
Модуль прогнозирования approval rate для CPA кампаний
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


class ApprovalRatePredictor(BaseModule):
    """
    Прогнозирование approval rate для CPA кампаний.

    Анализирует исторический approval rate (a_leads / leads * 100) и
    прогнозирует его изменение на следующие 3-7 дней используя линейную регрессию.

    Критерии:
    - Только CPA кампании (где sum(a_leads) > 0)
    - Минимум 10 лидов за период
    - История 14 дней (по умолчанию)
    - Прогноз на 7 дней вперед (по умолчанию)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="approval_rate_predictor",
            name="Прогноз апрувов",
            category="predictive",
            description="Прогнозирует approval rate для CPA кампаний на основе исторических данных",
            detailed_description="Модуль анализирует динамику approval rate (процент апрувов лидов) за исторический период и строит прогноз используя линейную регрессию. Помогает заранее выявить кампании с падающим апрувом. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["approval", "forecast", "prediction", "cpa", "trends"]
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
                "min_leads": 10,  # минимум лидов за период
                "history_days": 14,  # дней истории для анализа
                "forecast_days": 7  # дней для прогноза
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "min_leads": {
                "label": "Минимум лидов",
                "description": "Минимальное количество лидов за период",
                "type": "number",
                "min": 5,
                "max": 1000,
                "default": 10
            },
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

    def _calculate_forecast(self, historical_approve_rate: List[float], forecast_days: int) -> Dict[str, Any]:
        """
        Рассчитывает прогноз approval rate используя линейную регрессию.

        Args:
            historical_approve_rate: Список исторических значений approval rate
            forecast_days: Количество дней для прогноза

        Returns:
            Dict с прогнозными значениями или None если недостаточно данных
        """
        # Минимум 7 дней для значимого прогноза
        if len(historical_approve_rate) < 7:
            return None

        # Подготовка данных для регрессии
        x_values = list(range(len(historical_approve_rate)))
        y_values = historical_approve_rate

        # Линейная регрессия
        slope, intercept, r_squared = self._simple_linear_regression(x_values, y_values)

        # Прогноз
        forecast_values = []
        for i in range(forecast_days):
            day_offset = len(historical_approve_rate) + i
            predicted_rate = slope * day_offset + intercept

            # Ограничиваем диапазон 0-100%
            predicted_rate = max(0, min(100, predicted_rate))

            forecast_values.append({
                "day": i + 1,
                "predicted_approve_rate": round(predicted_rate, 2)
            })

        return {
            "forecast": forecast_values,
            "trend_slope": round(slope, 4),
            "r_squared": round(r_squared, 4),
            "avg_historical_approve_rate": round(np.mean(historical_approve_rate), 2)
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Прогнозирование approval rate для CPA кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Прогнозы approval rate для кампаний
        """
        # Получение параметров
        min_leads = config.params.get("min_leads", 10)
        history_days = config.params.get("history_days", 14)
        forecast_days = config.params.get("forecast_days", 7)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=history_days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с историей
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.a_leads,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.leads > 0  # только дни с лидами
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

                leads = row.leads
                a_leads = row.a_leads

                # Расчет approval rate для дня
                approve_rate = (a_leads / leads * 100) if leads > 0 else 0

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "leads": leads,
                    "a_leads": a_leads,
                    "approve_rate": approve_rate,
                    "clicks": row.clicks,
                    "cost": float(row.cost),
                    "revenue": float(row.revenue)
                })

            # Обработка и прогнозирование
            forecasts = []
            total_campaigns_analyzed = 0
            improving_forecasts = 0
            declining_forecasts = 0
            stable_forecasts = 0

            for campaign_id, data in campaigns_data.items():
                daily_stats = data["daily_stats"]

                # Считаем общую статистику
                total_leads = sum(d["leads"] for d in daily_stats)
                total_a_leads = sum(d["a_leads"] for d in daily_stats)

                # Фильтр 1: только CPA кампании (где есть approved leads)
                if total_a_leads == 0:
                    continue

                # Фильтр 2: минимум лидов за период
                if total_leads < min_leads:
                    continue

                # Извлекаем approve rate для прогноза
                historical_approve_rate = [d["approve_rate"] for d in daily_stats]

                # Рассчитываем прогноз
                forecast_result = self._calculate_forecast(
                    historical_approve_rate,
                    forecast_days
                )

                if not forecast_result:
                    continue

                # Агрегированная статистика
                total_cost = sum(d["cost"] for d in daily_stats)
                total_revenue = sum(d["revenue"] for d in daily_stats)
                current_approve_rate = historical_approve_rate[-1]  # последний день

                # Классификация тренда
                trend_slope = forecast_result["trend_slope"]
                if trend_slope > 0.1:
                    trend = "improving"
                    trend_label = "Улучшение"
                    improving_forecasts += 1
                elif trend_slope < -0.1:
                    trend = "declining"
                    trend_label = "Ухудшение"
                    declining_forecasts += 1
                else:
                    trend = "stable"
                    trend_label = "Стабильный"
                    stable_forecasts += 1

                # Прогноз на последний день
                last_forecast = forecast_result["forecast"][-1]

                forecasts.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_leads": total_leads,
                    "total_a_leads": total_a_leads,
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "current_approve_rate": round(current_approve_rate, 2),
                    "predicted_approve_rate": last_forecast["predicted_approve_rate"],
                    "trend": trend,
                    "trend_label": trend_label,
                    "trend_slope": forecast_result["trend_slope"],
                    "forecast": forecast_result["forecast"],
                    "r_squared": forecast_result["r_squared"],
                    "avg_historical_approve_rate": forecast_result["avg_historical_approve_rate"],
                    "days_of_data": len(daily_stats)
                })

                total_campaigns_analyzed += 1

            # Сортировка: сначала declining (падающий апрув - ОПАСНО!)
            forecasts.sort(key=lambda x: (
                0 if x["trend"] == "declining" else 1 if x["trend"] == "stable" else 2,
                x["trend_slope"]
            ))

            return {
                "forecasts": forecasts,
                "summary": {
                    "total_analyzed": total_campaigns_analyzed,
                    "improving_count": improving_forecasts,
                    "declining_count": declining_forecasts,
                    "stable_count": stable_forecasts,
                    "avg_r_squared": round(np.mean([f["r_squared"] for f in forecasts]), 3) if forecasts else 0
                },
                "period": {
                    "history_days": history_days,
                    "forecast_days": forecast_days,
                    "date_from": date_from.isoformat(),
                    "date_to": (datetime.now().date() + timedelta(days=forecast_days)).isoformat()
                },
                "params": {
                    "min_leads": min_leads
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

        # График прогнозов для топ-5 кампаний
        for idx, forecast_data in enumerate(forecasts):
            forecast_points = forecast_data["forecast"]

            charts.append({
                "id": f"approve_forecast_chart_{idx}",
                "type": "line",
                "data": {
                    "labels": [f"День {f['day']}" for f in forecast_points],
                    "datasets": [
                        {
                            "label": "Прогноз Approve Rate",
                            "data": [f["predicted_approve_rate"] for f in forecast_points],
                            "borderColor": "rgba(255, 99, 132, 1)",
                            "backgroundColor": "rgba(255, 99, 132, 0.2)",
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
                                "text": "Approve Rate (%)"
                            },
                            "min": 0,
                            "max": 100
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для прогнозов с падающим апрувом.
        """
        forecasts = raw_data.get("forecasts", [])
        alerts = []

        # Находим кампании с прогнозом падения апрува
        declining = [f for f in forecasts if f["trend"] == "declining"]

        if declining:
            # Берем топ-3 с самым сильным падением
            top_declining = sorted(declining, key=lambda x: x["trend_slope"])[:3]

            message = f"Прогноз показывает падение approval rate для {len(declining)} CPA кампаний\n\n"
            message += "Топ-3 с наибольшим падением:\n"

            for i, campaign in enumerate(top_declining, 1):
                message += f"{i}. {campaign['name']}: "
                message += f"текущий {campaign['current_approve_rate']:.1f}% -> "
                message += f"прогноз {campaign['predicted_approve_rate']:.1f}% "
                message += f"(тренд: {campaign['trend_slope']:.2f}%/день)\n"

            alerts.append({
                "type": "approve_rate_declining",
                "severity": "high" if len(declining) > 5 else "medium",
                "message": message,
                "recommended_action": "Проверьте качество трафика и условия у оффера",
                "campaigns_count": len(declining),
                "avg_decline": round(np.mean([c["trend_slope"] for c in declining]), 2)
            })

        return alerts
