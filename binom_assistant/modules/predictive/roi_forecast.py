"""
Модуль прогнозирования ROI на 3-7 дней вперед
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


class ROIForecast(BaseModule):
    """
    Прогнозирование ROI на несколько дней вперед.

    Использует исторические данные за последние 30 дней для прогноза ROI.
    Применяет простую линейную экстраполяцию с учетом тренда.

    Критерии:
    - Минимум 7 дней истории
    - Минимум $1/день расхода
    - Прогноз на 3-7 дней вперед (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="roi_forecast",
            name="Прогноз окупаемости",
            category="predictive",
            description="Прогнозирует ROI на 3-7 дней вперед на основе исторических данных",
            detailed_description="Модуль анализирует динамику ROI за последние 30 дней и строит прогноз используя линейную экстраполяцию с учетом тренда и сезонности.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["roi", "forecast", "prediction", "trends"]
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
                "history_days": 30,  # дней истории для анализа
                "forecast_days": 7,  # дней для прогноза
                "min_history_days": 7,  # минимум дней с данными
                "min_daily_spend": 1,  # минимум $1/день
                "confidence_level": 80,  # уровень доверительного интервала (%)
                "severity_high": -20,  # ROI для high severity
                "severity_medium": 0  # ROI для medium severity
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
                "default": 30
            },
            "forecast_days": {
                "label": "Дней прогноза",
                "description": "На сколько дней вперед строить прогноз",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "min_history_days": {
                "label": "Минимум дней с данными",
                "description": "Минимальное количество дней с активностью для прогноза",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 7
            },
            "min_daily_spend": {
                "label": "Минимальный расход/день",
                "description": "Минимальный средний расход в день ($)",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "default": 1
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

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "predicted_roi",
            "metric_label": "Прогнозируемый ROI",
            "metric_unit": "%",
            "description": "Пороги критичности на основе прогнозируемого ROI кампании",
            "thresholds": {
                "severity_high": {
                    "label": "Высокий ROI",
                    "description": "ROI ниже этого значения считается высокой важности",
                    "type": "number",
                    "min": -100,
                    "max": 0,
                    "step": 5,
                    "default": -20
                },
                "severity_medium": {
                    "label": "Средний ROI",
                    "description": "ROI ниже этого значения (но выше высокого) считается средней важности",
                    "type": "number",
                    "min": -100,
                    "max": 100,
                    "step": 5,
                    "default": 0
                }
            },
            "levels": [
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "ROI < high"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "high <= ROI < medium"},
                {"value": "low", "label": "Низкий", "color": "#10b981", "condition": "ROI >= medium"}
            ]
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

    def _calculate_forecast(self, historical_roi: List[float], forecast_days: int, confidence_level: int) -> Dict[str, Any]:
        """
        Рассчитывает прогноз ROI используя линейную регрессию.

        Args:
            historical_roi: Список исторических значений ROI
            forecast_days: Количество дней для прогноза
            confidence_level: Уровень доверительного интервала (не используется)

        Returns:
            Dict с прогнозными значениями
        """
        # Минимум 7 дней для значимого прогноза
        if len(historical_roi) < 7:
            return None

        # Подготовка данных для регрессии
        x_values = list(range(len(historical_roi)))
        y_values = historical_roi

        # Линейная регрессия
        slope, intercept, r_squared = self._simple_linear_regression(x_values, y_values)

        # Расчет стандартного отклонения для информации
        std_dev = np.std(historical_roi)

        # Прогноз
        forecast_values = []
        for i in range(forecast_days):
            day_offset = len(historical_roi) + i
            predicted_roi = slope * day_offset + intercept

            forecast_values.append({
                "day": i + 1,
                "predicted_roi": round(predicted_roi, 2)
            })

        return {
            "forecast": forecast_values,
            "trend_slope": round(slope, 4),
            "r_squared": round(r_squared, 4),
            "avg_historical_roi": round(np.mean(historical_roi), 2),
            "std_dev": round(std_dev, 2)
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Прогнозирование ROI для активных кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Прогнозы ROI для кампаний
        """
        # Получение параметров
        history_days = config.params.get("history_days", 30)
        forecast_days = config.params.get("forecast_days", 7)
        min_history_days = config.params.get("min_history_days", 7)
        min_daily_spend = config.params.get("min_daily_spend", 1)
        confidence_level = config.params.get("confidence_level", 80)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", -20)
        severity_medium_threshold = config.params.get("severity_medium", 0)

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
                CampaignStatsDaily.cost > 0
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

                cost = float(row.cost)
                revenue = float(row.revenue)
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "roi": roi,
                    "clicks": row.clicks,
                    "leads": row.leads
                })

            # Обработка и прогнозирование
            forecasts = []
            total_campaigns_analyzed = 0
            improving_forecasts = 0
            declining_forecasts = 0
            stable_forecasts = 0

            for campaign_id, data in campaigns_data.items():
                daily_stats = data["daily_stats"]

                # Фильтрация: минимум дней с данными
                if len(daily_stats) < min_history_days:
                    continue

                # Фильтрация: средний расход
                avg_daily_spend = sum(d["cost"] for d in daily_stats) / len(daily_stats)
                if avg_daily_spend < min_daily_spend:
                    continue

                # Извлекаем ROI для прогноза
                historical_roi = [d["roi"] for d in daily_stats]

                # Рассчитываем прогноз
                forecast_result = self._calculate_forecast(
                    historical_roi,
                    forecast_days,
                    confidence_level
                )

                if not forecast_result:
                    continue

                # Агрегированная статистика
                total_cost = sum(d["cost"] for d in daily_stats)
                total_revenue = sum(d["revenue"] for d in daily_stats)
                avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

                # Классификация тренда
                trend_slope = forecast_result["trend_slope"]
                if trend_slope > 0.5:
                    trend = "improving"
                    trend_label = "Улучшение"
                    improving_forecasts += 1
                elif trend_slope < -0.5:
                    trend = "declining"
                    trend_label = "Ухудшение"
                    declining_forecasts += 1
                else:
                    trend = "stable"
                    trend_label = "Стабильный"
                    stable_forecasts += 1

                # Определение критичности на основе настраиваемых порогов
                last_forecast = forecast_result["forecast"][-1]
                if last_forecast["predicted_roi"] < severity_high_threshold:
                    severity = "high"
                elif last_forecast["predicted_roi"] < severity_medium_threshold:
                    severity = "medium"
                else:
                    severity = "low"

                forecasts.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "avg_roi": round(avg_roi, 2),
                    "current_roi": round(historical_roi[-1], 2),
                    "forecast": forecast_result["forecast"],
                    "trend": trend,
                    "trend_label": trend_label,
                    "trend_slope": forecast_result["trend_slope"],
                    "r_squared": forecast_result["r_squared"],
                    "avg_historical_roi": forecast_result["avg_historical_roi"],
                    "std_dev": forecast_result["std_dev"],
                    "days_of_data": len(daily_stats),
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "severity": severity
                })

                total_campaigns_analyzed += 1

            # Сортировка: сначала ухудшающиеся
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
                    "min_history_days": min_history_days,
                    "min_daily_spend": min_daily_spend,
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

        # График прогнозов для топ-5 кампаний
        for idx, forecast_data in enumerate(forecasts):
            forecast_points = forecast_data["forecast"]

            charts.append({
                "id": f"forecast_chart_{idx}",
                "type": "line",
                "data": {
                    "labels": [f"День {f['day']}" for f in forecast_points],
                    "datasets": [
                        {
                            "label": "Прогноз ROI",
                            "data": [f["predicted_roi"] for f in forecast_points],
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
                                "text": "ROI (%)"
                            }
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для прогнозов с ухудшением.
        """
        forecasts = raw_data.get("forecasts", [])
        alerts = []

        # Находим кампании с прогнозом ухудшения
        declining = [f for f in forecasts if f["trend"] == "declining"]

        if declining:
            # Берем топ-3 с самым сильным ухудшением
            top_declining = sorted(declining, key=lambda x: x["trend_slope"])[:3]

            message = f"Прогноз показывает ухудшение для {len(declining)} кампаний\n\n"
            message += "Топ-3 с наибольшим падением:\n"

            for i, campaign in enumerate(top_declining, 1):
                last_forecast = campaign["forecast"][-1]
                message += f"{i}. {campaign['name']}: "
                message += f"текущий ROI {campaign['current_roi']:.1f}% → "
                message += f"прогноз {last_forecast['predicted_roi']:.1f}% "
                message += f"(тренд: {campaign['trend_slope']:.2f})\n"

            alerts.append({
                "type": "roi_forecast_declining",
                "severity": "high" if len(declining) > 5 else "medium",
                "message": message,
                "recommended_action": "Проанализируйте причины падения и рассмотрите корректировку стратегии",
                "campaigns_count": len(declining),
                "avg_decline": round(np.mean([c["trend_slope"] for c in declining]), 2)
            })

        return alerts
