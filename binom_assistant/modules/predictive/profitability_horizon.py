"""
Модуль прогнозирования выхода в безубыточность
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


class ProfitabilityHorizon(BaseModule):
    """
    Прогнозирование выхода в безубыточность (ROI = 0).

    Анализирует кампании с отрицательным ROI но положительным трендом
    и рассчитывает через сколько дней они выйдут в плюс.

    Критерии:
    - Текущий ROI < 0 (убыточные)
    - Тренд ROI положительный (ROI растет)
    - Минимум 7 дней истории
    - Минимальный расход
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="profitability_horizon",
            name="До безубыточности",
            category="predictive",
            description="Прогноз выхода в безубыточность (ROI = 0)",
            detailed_description="Модуль анализирует кампании с отрицательным ROI и положительным трендом, рассчитывает через сколько дней они выйдут в ноль используя линейную регрессию.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["roi", "breakeven", "prediction", "profitability"]
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
                "min_spend": 5,  # минимальный расход ($)
                "days_history": 7,  # дней истории для тренда
                "min_trend": 1.0,  # минимальный тренд (ROI/день)
                "min_r_squared": 0.3  # минимальная точность модели
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "min_spend": {
                "label": "Минимальный расход",
                "description": "Минимальный общий расход за период ($)",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 5
            },
            "days_history": {
                "label": "Дней истории",
                "description": "Количество дней истории для анализа тренда",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 7
            },
            "min_trend": {
                "label": "Минимальный тренд",
                "description": "Минимальный рост ROI в день (%)",
                "type": "number",
                "min": 0.1,
                "max": 10,
                "default": 1.0
            },
            "min_r_squared": {
                "label": "Минимальная точность",
                "description": "Минимальный R² для уверенности в прогнозе",
                "type": "number",
                "min": 0.1,
                "max": 1.0,
                "default": 0.3
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

    def _calculate_breakeven(self, historical_roi: List[float], current_roi: float) -> Dict[str, Any]:
        """
        Рассчитывает дни до безубыточности используя линейную регрессию.

        Args:
            historical_roi: Список исторических значений ROI
            current_roi: Текущий ROI

        Returns:
            Dict с прогнозом выхода в безубыточность или None
        """
        # Минимум 7 дней для значимого прогноза
        if len(historical_roi) < 7:
            return None

        # Подготовка данных для регрессии
        x_values = list(range(len(historical_roi)))
        y_values = historical_roi

        # Линейная регрессия
        slope, intercept, r_squared = self._simple_linear_regression(x_values, y_values)

        # Проверяем что тренд положительный (ROI растет)
        if slope <= 0:
            return None

        # Рассчитываем дни до ROI = 0
        # Текущий ROI известен, нужно найти сколько дней до достижения ROI = 0
        # Используем формулу: days = (target_roi - current_roi) / slope
        # Для безубыточности: days = (0 - current_roi) / slope = -current_roi / slope

        # Рассчитываем дни от текущего ROI до нуля
        days_to_breakeven = -current_roi / slope

        # Если уже в плюсе или расчет некорректен
        if days_to_breakeven <= 0:
            return None

        # Прогнозируемая дата
        projected_date = datetime.now().date() + timedelta(days=int(days_to_breakeven))

        return {
            "days_to_breakeven": round(days_to_breakeven, 1),
            "projected_date": projected_date.isoformat(),
            "roi_trend": round(slope, 3),
            "r_squared": round(r_squared, 3),
            "confidence": "high" if r_squared > 0.7 else "medium" if r_squared > 0.4 else "low"
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Прогнозирование выхода в безубыточность для убыточных кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Прогнозы выхода в безубыточность
        """
        # Получение параметров
        min_spend = config.params.get("min_spend", 5)
        days_history = config.params.get("days_history", 7)
        min_trend = config.params.get("min_trend", 1.0)
        min_r_squared = config.params.get("min_r_squared", 0.3)

        date_from = datetime.now().date() - timedelta(days=days_history - 1)

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
            breakeven_forecasts = []
            total_campaigns_analyzed = 0
            total_negative_roi = 0
            total_with_positive_trend = 0

            for campaign_id, data in campaigns_data.items():
                daily_stats = data["daily_stats"]

                # Фильтрация: минимум 7 дней с данными для значимого прогноза
                if len(daily_stats) < 7:
                    continue

                # Фильтрация: минимальный расход
                total_cost = sum(d["cost"] for d in daily_stats)
                if total_cost < min_spend:
                    continue

                # Извлекаем ROI для анализа
                historical_roi = [d["roi"] for d in daily_stats]
                current_roi = historical_roi[-1]

                # Агрегированная статистика
                total_revenue = sum(d["revenue"] for d in daily_stats)
                avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

                total_campaigns_analyzed += 1

                # Фильтр: только кампании с отрицательным ROI
                if current_roi >= 0:
                    continue

                total_negative_roi += 1

                # Рассчитываем прогноз выхода в безубыточность
                breakeven_result = self._calculate_breakeven(historical_roi, current_roi)

                if not breakeven_result:
                    continue

                # Фильтр: минимальный тренд
                if breakeven_result["roi_trend"] < min_trend:
                    continue

                # Фильтр: минимальная точность модели
                if breakeven_result["r_squared"] < min_r_squared:
                    continue

                total_with_positive_trend += 1

                # Определение приоритета
                days_to_breakeven = breakeven_result["days_to_breakeven"]
                if days_to_breakeven <= 3:
                    priority = "high"
                    priority_label = "Скоро"
                elif days_to_breakeven <= 7:
                    priority = "medium"
                    priority_label = "Средний"
                else:
                    priority = "low"
                    priority_label = "Долгий"

                breakeven_forecasts.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "avg_roi": round(avg_roi, 2),
                    "current_roi": round(current_roi, 2),
                    "roi_trend": breakeven_result["roi_trend"],
                    "days_to_breakeven": breakeven_result["days_to_breakeven"],
                    "projected_date": breakeven_result["projected_date"],
                    "r_squared": breakeven_result["r_squared"],
                    "confidence": breakeven_result["confidence"],
                    "days_of_data": len(daily_stats),
                    "priority": priority,
                    "priority_label": priority_label
                })

            # Сортировка: сначала те, кто быстрее выйдет в плюс
            breakeven_forecasts.sort(key=lambda x: x["days_to_breakeven"])

            return {
                "results": breakeven_forecasts,
                "summary": {
                    "total_analyzed": total_campaigns_analyzed,
                    "negative_roi_count": total_negative_roi,
                    "with_positive_trend": total_with_positive_trend,
                    "breakeven_forecasts": len(breakeven_forecasts),
                    "avg_days_to_breakeven": round(np.mean([f["days_to_breakeven"] for f in breakeven_forecasts]), 1) if breakeven_forecasts else 0,
                    "fastest_breakeven": round(min([f["days_to_breakeven"] for f in breakeven_forecasts]), 1) if breakeven_forecasts else 0
                },
                "period": {
                    "days_history": days_history,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_spend": min_spend,
                    "min_trend": min_trend,
                    "min_r_squared": min_r_squared
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        results = raw_data.get("results", [])[:10]  # Топ-10

        if not results:
            return []

        charts = []

        # График: дни до безубыточности
        charts.append({
            "id": "breakeven_days_chart",
            "type": "bar",
            "data": {
                "labels": [f"{r['name'][:25]}..." if len(r['name']) > 25 else r['name'] for r in results],
                "datasets": [
                    {
                        "label": "Дней до безубыточности",
                        "data": [r["days_to_breakeven"] for r in results],
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.7)" if r["priority"] == "high" else
                            "rgba(255, 206, 86, 0.7)" if r["priority"] == "medium" else
                            "rgba(75, 192, 192, 0.7)"
                            for r in results
                        ],
                        "borderColor": [
                            "rgba(255, 99, 132, 1)" if r["priority"] == "high" else
                            "rgba(255, 206, 86, 1)" if r["priority"] == "medium" else
                            "rgba(75, 192, 192, 1)"
                            for r in results
                        ],
                        "borderWidth": 1
                    }
                ]
            },
            "options": {
                "indexAxis": "y",
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 кампаний по скорости выхода в безубыточность"
                    },
                    "legend": {
                        "display": False
                    }
                },
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": "Дней"
                        }
                    }
                }
            }
        })

        # График: текущий ROI vs тренд
        charts.append({
            "id": "roi_trend_chart",
            "type": "scatter",
            "data": {
                "datasets": [
                    {
                        "label": "Кампании",
                        "data": [
                            {"x": r["current_roi"], "y": r["roi_trend"], "label": r["name"][:30]}
                            for r in results
                        ],
                        "backgroundColor": "rgba(54, 162, 235, 0.5)",
                        "borderColor": "rgba(54, 162, 235, 1)"
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Текущий ROI vs Скорость роста"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "(context) => context.raw.label"
                        }
                    }
                },
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": "Текущий ROI (%)"
                        }
                    },
                    "y": {
                        "title": {
                            "display": True,
                            "text": "Тренд ROI (%/день)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний близких к безубыточности.
        """
        results = raw_data.get("results", [])
        alerts = []

        # Находим кампании которые скоро выйдут в плюс (< 3 дней)
        soon_breakeven = [r for r in results if r["days_to_breakeven"] <= 3]

        if soon_breakeven:
            message = f"Найдено {len(soon_breakeven)} кампаний, которые скоро выйдут в безубыточность\n\n"
            message += "Топ-3:\n"

            for i, campaign in enumerate(soon_breakeven[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"текущий ROI {campaign['current_roi']:.1f}% → "
                message += f"безубыточность через {campaign['days_to_breakeven']:.1f} дней "
                message += f"({campaign['projected_date']})\n"

            alerts.append({
                "type": "profitability_horizon_soon",
                "severity": "low",
                "message": message,
                "recommended_action": "Следите за этими кампаниями, они скоро станут прибыльными",
                "campaigns_count": len(soon_breakeven),
                "avg_days": round(np.mean([c["days_to_breakeven"] for c in soon_breakeven]), 1)
            })

        return alerts
