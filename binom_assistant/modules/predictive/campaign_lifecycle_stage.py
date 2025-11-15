"""
Модуль определения стадии жизненного цикла кампании
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


class CampaignLifecycleStage(BaseModule):
    """
    Определение стадии жизненного цикла кампании.

    Классифицирует кампании по стадиям:
    - Launch (запуск): < 3 дней активности
    - Growth (рост): ROI растет, расход растет
    - Maturity (зрелость): стабильный ROI, стабильный расход
    - Decline (упадок): ROI падает
    - Stagnation (застой): низкий расход, низкий ROI
    - Dead (мертвая): нет расхода последние N дней

    Критерии:
    - Минимум min_spend общего расхода
    - Анализ за последние days_history дней
    - Линейная регрессия для определения трендов
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="campaign_lifecycle_stage",
            name="Этап кампании",
            category="predictive",
            description="Определяет стадию жизненного цикла кампании",
            detailed_description="Модуль классифицирует кампании по стадиям: запуск, рост, зрелость, упадок, застой, мертвая. Использует линейную регрессию для анализа трендов ROI и расходов.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["lifecycle", "stage", "classification", "trends"]
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
                "min_spend": 5,  # минимальный расход для анализа
                "days_history": 14,  # дней для анализа
                "stagnation_threshold": 1  # порог застоя ($)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "min_spend": {
                "label": "Минимальный расход",
                "description": "Минимальный общий расход для анализа ($)",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 5
            },
            "days_history": {
                "label": "Дней истории",
                "description": "Количество дней для анализа",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "stagnation_threshold": {
                "label": "Порог застоя",
                "description": "Средний расход/день ниже которого кампания считается застойной ($)",
                "type": "number",
                "min": 0.1,
                "max": 10,
                "default": 1
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

    def _determine_stage(self, daily_stats: List[Dict], params: Dict) -> Dict[str, Any]:
        """
        Определяет стадию жизненного цикла кампании.

        Args:
            daily_stats: Список дневной статистики
            params: Параметры анализа

        Returns:
            Dict с информацией о стадии
        """
        stagnation_threshold = params.get("stagnation_threshold", 1)

        # Подсчет дней активности (дни с cost > 0)
        active_days = [d for d in daily_stats if d["cost"] > 0]
        days_active = len(active_days)

        if days_active == 0:
            return {
                "stage": "dead",
                "stage_label": "Мертвая",
                "days_active": 0,
                "roi_trend": 0,
                "spend_trend": 0,
                "confidence": 1.0
            }

        # Расчет последних 7 дней
        last_7_days = daily_stats[-7:] if len(daily_stats) >= 7 else daily_stats
        last_7_days_cost = sum(d["cost"] for d in last_7_days)

        # Расчет средних значений
        total_cost = sum(d["cost"] for d in daily_stats)
        total_revenue = sum(d["revenue"] for d in daily_stats)
        avg_daily_spend = total_cost / len(daily_stats) if len(daily_stats) > 0 else 0
        avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

        # СТАДИЯ: Launch (< 3 дней активности)
        if days_active < 3:
            return {
                "stage": "launch",
                "stage_label": "Запуск",
                "days_active": days_active,
                "roi_trend": 0,
                "spend_trend": 0,
                "confidence": 0.8
            }

        # СТАДИЯ: Dead (нет расхода последние 7 дней)
        if last_7_days_cost == 0:
            return {
                "stage": "dead",
                "stage_label": "Мертвая",
                "days_active": days_active,
                "roi_trend": 0,
                "spend_trend": 0,
                "confidence": 1.0
            }

        # Расчет трендов используя линейную регрессию
        if days_active >= 2:
            # Подготовка данных для регрессии (только активные дни)
            x_values = list(range(len(active_days)))
            roi_values = [d["roi"] for d in active_days]
            cost_values = [d["cost"] for d in active_days]

            # ROI тренд
            roi_slope, _, roi_r_squared = self._simple_linear_regression(x_values, roi_values)

            # Cost тренд
            cost_slope, _, cost_r_squared = self._simple_linear_regression(x_values, cost_values)

            # Confidence основан на R² обоих трендов
            confidence = (roi_r_squared + cost_r_squared) / 2
        else:
            roi_slope = 0
            cost_slope = 0
            confidence = 0.5

        # СТАДИЯ: Stagnation (низкий расход и низкий ROI)
        if avg_daily_spend < stagnation_threshold and avg_roi < 0:
            return {
                "stage": "stagnation",
                "stage_label": "Застой",
                "days_active": days_active,
                "roi_trend": round(roi_slope, 2),
                "spend_trend": round(cost_slope, 2),
                "confidence": round(confidence, 2)
            }

        # СТАДИЯ: Growth (ROI растет и расход растет)
        if roi_slope > 5 and cost_slope > 0:
            return {
                "stage": "growth",
                "stage_label": "Рост",
                "days_active": days_active,
                "roi_trend": round(roi_slope, 2),
                "spend_trend": round(cost_slope, 2),
                "confidence": round(confidence, 2)
            }

        # СТАДИЯ: Decline (ROI падает)
        if roi_slope < -5:
            return {
                "stage": "decline",
                "stage_label": "Упадок",
                "days_active": days_active,
                "roi_trend": round(roi_slope, 2),
                "spend_trend": round(cost_slope, 2),
                "confidence": round(confidence, 2)
            }

        # СТАДИЯ: Maturity (по умолчанию - стабильная)
        return {
            "stage": "maturity",
            "stage_label": "Зрелость",
            "days_active": days_active,
            "roi_trend": round(roi_slope, 2),
            "spend_trend": round(cost_slope, 2),
            "confidence": round(confidence, 2)
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Определение стадий жизненного цикла для активных кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Классификация кампаний по стадиям
        """
        # Получение параметров
        min_spend = config.params.get("min_spend", 5)
        days_history = config.params.get("days_history", 14)
        stagnation_threshold = config.params.get("stagnation_threshold", 1)

        date_from = datetime.now().date() - timedelta(days=days_history - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с историей
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
                CampaignStatsDaily.date >= date_from
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

            # Обработка и классификация
            campaign_stages = []

            # Счетчики по стадиям
            stage_counts = {
                "launch": 0,
                "growth": 0,
                "maturity": 0,
                "decline": 0,
                "stagnation": 0,
                "dead": 0
            }

            for campaign_id, data in campaigns_data.items():
                daily_stats = data["daily_stats"]

                # Фильтрация: минимальный расход
                total_cost = sum(d["cost"] for d in daily_stats)
                if total_cost < min_spend:
                    continue

                # Определяем стадию
                stage_info = self._determine_stage(
                    daily_stats,
                    {"stagnation_threshold": stagnation_threshold}
                )

                # Агрегированная статистика
                total_revenue = sum(d["revenue"] for d in daily_stats)
                avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
                avg_daily_spend = total_cost / days_history if days_history > 0 else 0

                campaign_stages.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "stage": stage_info["stage"],
                    "stage_label": stage_info["stage_label"],
                    "days_active": stage_info["days_active"],
                    "roi_trend": stage_info["roi_trend"],
                    "spend_trend": stage_info["spend_trend"],
                    "confidence": stage_info["confidence"],
                    "current_roi": round(avg_roi, 2),
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2)
                })

                # Обновляем счетчики
                stage_counts[stage_info["stage"]] += 1

            # Сортировка по приоритету: decline > stagnation > dead > launch > growth > maturity
            priority_map = {
                "decline": 0,
                "stagnation": 1,
                "dead": 2,
                "launch": 3,
                "growth": 4,
                "maturity": 5
            }

            campaign_stages.sort(key=lambda x: (
                priority_map.get(x["stage"], 99),
                -x["total_cost"]  # внутри группы - по убыванию расхода
            ))

            return {
                "campaigns": campaign_stages,
                "summary": {
                    "total_analyzed": len(campaign_stages),
                    "launch_count": stage_counts["launch"],
                    "growth_count": stage_counts["growth"],
                    "maturity_count": stage_counts["maturity"],
                    "decline_count": stage_counts["decline"],
                    "stagnation_count": stage_counts["stagnation"],
                    "dead_count": stage_counts["dead"]
                },
                "period": {
                    "days_history": days_history,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_spend": min_spend,
                    "stagnation_threshold": stagnation_threshold
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        summary = raw_data.get("summary", {})

        if not summary:
            return []

        # График распределения по стадиям
        stage_counts = [
            summary.get("launch_count", 0),
            summary.get("growth_count", 0),
            summary.get("maturity_count", 0),
            summary.get("decline_count", 0),
            summary.get("stagnation_count", 0),
            summary.get("dead_count", 0)
        ]

        return [{
            "id": "lifecycle_stages_chart",
            "type": "doughnut",
            "data": {
                "labels": ["Запуск", "Рост", "Зрелость", "Упадок", "Застой", "Мертвая"],
                "datasets": [{
                    "label": "Количество кампаний",
                    "data": stage_counts,
                    "backgroundColor": [
                        "rgba(54, 162, 235, 0.8)",   # Запуск - синий
                        "rgba(75, 192, 192, 0.8)",   # Рост - зеленый
                        "rgba(153, 102, 255, 0.8)",  # Зрелость - фиолетовый
                        "rgba(255, 99, 132, 0.8)",   # Упадок - красный
                        "rgba(255, 206, 86, 0.8)",   # Застой - желтый
                        "rgba(201, 203, 207, 0.8)"   # Мертвая - серый
                    ],
                    "borderColor": [
                        "rgba(54, 162, 235, 1)",
                        "rgba(75, 192, 192, 1)",
                        "rgba(153, 102, 255, 1)",
                        "rgba(255, 99, 132, 1)",
                        "rgba(255, 206, 86, 1)",
                        "rgba(201, 203, 207, 1)"
                    ],
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение кампаний по стадиям"
                    },
                    "legend": {
                        "position": "right"
                    }
                }
            }
        }]

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний в стадии упадка.
        """
        campaigns = raw_data.get("campaigns", [])
        alerts = []

        # Находим кампании в стадии упадка
        declining = [c for c in campaigns if c["stage"] == "decline"]

        if declining:
            # Берем топ-3 с наибольшими расходами
            top_declining = sorted(declining, key=lambda x: x["total_cost"], reverse=True)[:3]

            message = f"Обнаружено {len(declining)} кампаний в стадии упадка\n\n"
            message += "Топ-3 по расходам:\n"

            for i, campaign in enumerate(top_declining, 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['current_roi']:.1f}%, "
                message += f"тренд {campaign['roi_trend']:.2f}%/день, "
                message += f"расход ${campaign['total_cost']:.2f}\n"

            alerts.append({
                "type": "lifecycle_decline",
                "severity": "high" if len(declining) > 5 else "medium",
                "message": message,
                "recommended_action": "Рассмотрите оптимизацию или остановку кампаний в стадии упадка",
                "campaigns_count": len(declining),
                "avg_roi_trend": round(np.mean([c["roi_trend"] for c in declining]), 2)
            })

        # Алерт для застойных кампаний
        stagnant = [c for c in campaigns if c["stage"] == "stagnation"]

        if stagnant:
            total_stagnant_spend = sum(c["total_cost"] for c in stagnant)

            message = f"Обнаружено {len(stagnant)} застойных кампаний\n"
            message += f"Общий расход: ${total_stagnant_spend:.2f}\n"
            message += "Эти кампании имеют низкий расход и отрицательный ROI"

            alerts.append({
                "type": "lifecycle_stagnation",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите перераспределение бюджета или остановку застойных кампаний",
                "campaigns_count": len(stagnant),
                "total_spend": round(total_stagnant_spend, 2)
            })

        return alerts
