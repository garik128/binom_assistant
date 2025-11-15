"""
Модуль отслеживания жизненного цикла офферов (Offer Lifecycle Tracker)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from contextlib import contextmanager
from collections import defaultdict
import statistics

from storage.database.base import get_session
from storage.database.models import Offer, OfferStatsDaily, AffiliateNetwork
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


class OfferLifecycleTracker(BaseModule):
    """
    Модуль отслеживания жизненного цикла офферов (Offer Lifecycle Tracker).

    Определяет стадию жизненного цикла офферов на основе:
    - Продолжительность активности
    - Тренд ROI и объемов
    - Стабильность показателей
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="offer_lifecycle_tracker",
            name="Цикл оффера",
            category="sources_offers",
            description="Определяет стадию жизни офферов",
            detailed_description="Модуль анализирует жизненный цикл офферов и определяет их стадию: новый, растущий, зрелый, умирающий или мертвый. Помогает принять решения по скейлированию или закрытию офферов.",
            version="1.1.0",
            author="Binom Assistant",
            priority="medium",
            tags=["offers", "lifecycle", "stage", "roi", "trends", "revenue"]
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
                "days": 14,
                "min_days_active": 3,
                "min_cost": 1.0,  # минимальный расход для анализа
                "new_stage_days": 7,  # порог для стадии "новый" (<)
                "mature_stage_days": 14,  # порог для стадии "зрелый" (>)
                "dying_stage_days": 7,  # порог для стадии "умирающий" (>)
                "dead_stage_days": 5  # порог для подсчета последних дней (>)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа цикла оффера",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "min_days_active": {
                "label": "Минимум дней активности",
                "description": "Минимальное количество дней с данными для включения оффера в анализ",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 3
            },
            "min_cost": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход для включения оффера в анализ",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "default": 1.0
            },
            "new_stage_days": {
                "label": "Дней для стадии 'Новый'",
                "description": "Максимальное количество дней активности для стадии 'Новый'",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "mature_stage_days": {
                "label": "Дней для стадии 'Зрелый'",
                "description": "Минимальное количество дней активности для стадии 'Зрелый'",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "dying_stage_days": {
                "label": "Дней для стадии 'Умирающий'",
                "description": "Минимальное количество дней снижения для стадии 'Умирающий'",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "dead_stage_days": {
                "label": "Дней для анализа тренда",
                "description": "Количество последних дней для анализа тренда оффера",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 5
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ жизненного цикла офферов.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о жизненном цикле офферов
        """
        # Получение параметров
        days = config.params.get("days", 14)
        min_days_active = config.params.get("min_days_active", 3)
        min_cost = config.params.get("min_cost", 1.0)
        new_stage_days = config.params.get("new_stage_days", 7)
        mature_stage_days = config.params.get("mature_stage_days", 14)
        dying_stage_days = config.params.get("dying_stage_days", 7)
        dead_stage_days = config.params.get("dead_stage_days", 5)

        date_from = datetime.now().date() - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем данные по офферам за период
            query = session.query(
                Offer.id,
                Offer.name,
                Offer.network_id,
                Offer.geo,
                Offer.payout,
                OfferStatsDaily.date,
                OfferStatsDaily.cost,
                OfferStatsDaily.revenue,
                OfferStatsDaily.leads,
                OfferStatsDaily.a_leads,
                OfferStatsDaily.clicks
            ).join(
                OfferStatsDaily,
                Offer.id == OfferStatsDaily.offer_id
            ).filter(
                OfferStatsDaily.date >= date_from
            ).order_by(
                Offer.id,
                OfferStatsDaily.date
            )

            results = query.all()

            # Группировка по офферам
            offers_data = defaultdict(lambda: {
                "offer_name": None,
                "network_id": None,
                "geo": None,
                "payout": None,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "total_clicks": 0,
                "days_with_data": 0,
                "daily_stats": [],
                "first_date": None,
                "last_date": None
            })

            for row in results:
                offer_id = row.id

                # Инициализация данных оффера
                if offers_data[offer_id]["offer_name"] is None:
                    offers_data[offer_id]["offer_name"] = row.name
                    offers_data[offer_id]["network_id"] = row.network_id
                    offers_data[offer_id]["geo"] = row.geo
                    offers_data[offer_id]["payout"] = float(row.payout) if row.payout else 0

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                leads = int(row.leads) if row.leads else 0
                a_leads = int(row.a_leads) if row.a_leads else 0
                clicks = int(row.clicks) if row.clicks else 0

                offers_data[offer_id]["total_cost"] += cost
                offers_data[offer_id]["total_revenue"] += revenue
                offers_data[offer_id]["total_leads"] += leads
                offers_data[offer_id]["total_a_leads"] += a_leads
                offers_data[offer_id]["total_clicks"] += clicks

                if cost > 0:
                    offers_data[offer_id]["days_with_data"] += 1
                    if offers_data[offer_id]["first_date"] is None:
                        offers_data[offer_id]["first_date"] = row.date
                    offers_data[offer_id]["last_date"] = row.date

                offers_data[offer_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads,
                    "clicks": clicks
                })

            # Анализ жизненного цикла
            lifecycle_offers = []

            for offer_id, data in offers_data.items():
                # Пропускаем офферы с недостаточными данными
                if data["days_with_data"] < min_days_active:
                    continue

                cost = data["total_cost"]
                revenue = data["total_revenue"]

                # Пропускаем очень маленькие офферы (шум)
                if cost < 1:
                    continue

                # Расчет основных метрик
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0

                # Расчет CR
                avg_cr = (data["total_leads"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0

                # Анализ дневных данных для трендов
                daily_roi_values = []
                daily_revenue_values = []
                for day_stat in data["daily_stats"]:
                    if day_stat["cost"] > 0:
                        day_roi = ((day_stat["revenue"] - day_stat["cost"]) / day_stat["cost"]) * 100
                        daily_roi_values.append(day_roi)
                        daily_revenue_values.append(day_stat["revenue"])

                # Определение стадии
                stage = self._determine_stage(
                    days_active=data["days_with_data"],
                    roi=roi,
                    avg_cr=avg_cr,
                    daily_roi_values=daily_roi_values,
                    daily_revenue_values=daily_revenue_values
                )

                # Определение трендов
                roi_trend = self._calculate_trend(daily_roi_values)
                revenue_trend = self._calculate_trend(daily_revenue_values)

                # Рекомендация
                recommendation = self._get_recommendation(
                    stage=stage,
                    roi=roi,
                    roi_trend=roi_trend,
                    revenue_trend=revenue_trend
                )

                lifecycle_offers.append({
                    "offer_id": offer_id,
                    "offer_name": data["offer_name"],
                    "network_id": data.get("network_id"),
                    "geo": data.get("geo"),
                    "stage": stage,
                    "days_active": data["days_with_data"],
                    "roi": round(roi, 2),
                    "avg_cr": round(avg_cr, 2),
                    "roi_trend": roi_trend,
                    "revenue_trend": revenue_trend,
                    "total_cost": round(cost, 2),
                    "total_revenue": round(revenue, 2),
                    "total_leads": int(data["total_leads"]),
                    "total_a_leads": int(data["total_a_leads"]),
                    "total_clicks": int(data["total_clicks"]),
                    "recommendation": recommendation
                })

            # Сортировка: сначала по стадии, потом по ROI
            stage_priority = {
                "new": 0,
                "growing": 1,
                "mature": 2,
                "declining": 3,
                "dead": 4
            }
            lifecycle_offers.sort(
                key=lambda x: (stage_priority.get(x["stage"], 5), -x["roi"]),
                reverse=False
            )

            # Подготовка итоговых данных
            period = {
                "from": date_from.isoformat(),
                "to": datetime.now().date().isoformat(),
                "days": days
            }

            summary = {
                "total_offers": len(lifecycle_offers),
                "new_offers": len([x for x in lifecycle_offers if x["stage"] == "new"]),
                "growing_offers": len([x for x in lifecycle_offers if x["stage"] == "growing"]),
                "mature_offers": len([x for x in lifecycle_offers if x["stage"] == "mature"]),
                "declining_offers": len([x for x in lifecycle_offers if x["stage"] == "declining"]),
                "dead_offers": len([x for x in lifecycle_offers if x["stage"] == "dead"]),
                "avg_roi": round(statistics.mean([x["roi"] for x in lifecycle_offers]) if lifecycle_offers else 0, 2),
                "total_cost": round(sum(x["total_cost"] for x in lifecycle_offers), 2),
                "total_revenue": round(sum(x["total_revenue"] for x in lifecycle_offers), 2),
                "total_leads": sum(x["total_leads"] for x in lifecycle_offers)
            }

            return {
                "offers": lifecycle_offers,
                "summary": summary,
                "period": period
            }

    def _determine_stage(
        self,
        days_active: int,
        roi: float,
        avg_cr: float,
        daily_roi_values: List[float],
        daily_revenue_values: List[float]
    ) -> str:
        """
        Определяет стадию жизненного цикла оффера.

        Логика:
        - Новый: < 7 дней активности
        - Растущий: ROI и объемы растут
        - Зрелый: стабильные показатели > 14 дней
        - Умирающий: снижение CR и ROI > 7 дней
        - Мертвый: ROI < 0 более 5 дней

        Args:
            days_active: Количество дней с данными
            roi: Общий ROI
            avg_cr: Средний CR
            daily_roi_values: Список дневных ROI
            daily_revenue_values: Список дневных доходов

        Returns:
            str: Стадия (new/growing/mature/declining/dead)
        """
        # Проверка мертвого оффера
        if len(daily_roi_values) > 5:
            last_5_roi = daily_roi_values[-5:]
            if all(r < 0 for r in last_5_roi):
                return "dead"

        # Проверка умирающего оффера
        if days_active > 7 and roi < 0:
            return "declining"

        # Проверка новой стадии
        if days_active < 7:
            return "new"

        # Анализ тренда ROI
        roi_trend = self._calculate_trend(daily_roi_values)
        revenue_trend = self._calculate_trend(daily_revenue_values)

        # Зрелый оффер: стабильные показатели, хороший ROI
        if days_active > 14 and roi > 0 and roi_trend in ["stable", "growing"]:
            return "mature"

        # Растущий оффер: позитивный тренд
        if roi_trend == "growing" and revenue_trend == "growing":
            return "growing"

        # Умирающий оффер: отрицательный тренд
        if roi_trend == "declining":
            return "declining"

        # По умолчанию - зрелый если есть данные
        if days_active > 7 and roi > 0:
            return "mature"

        return "growing"

    def _calculate_trend(self, values: List[float]) -> str:
        """
        Определяет тренд набора значений.

        Args:
            values: Список значений

        Returns:
            str: Тренд (growing/stable/declining)
        """
        if not values or len(values) < 2:
            return "stable"

        # Простой анализ: сравниваем первую и вторую половины
        mid = len(values) // 2
        if mid == 0:
            return "stable"

        first_half_avg = statistics.mean(values[:mid])
        second_half_avg = statistics.mean(values[mid:])

        # Вычисляем процент изменения
        if abs(first_half_avg) > 0:
            change_pct = ((second_half_avg - first_half_avg) / abs(first_half_avg)) * 100
        else:
            change_pct = 0 if second_half_avg == 0 else 100

        # Определяем тренд с учетом 10% порога
        if change_pct > 10:
            return "growing"
        elif change_pct < -10:
            return "declining"
        else:
            return "stable"

    def _get_recommendation(
        self,
        stage: str,
        roi: float,
        roi_trend: str,
        revenue_trend: str
    ) -> str:
        """
        Генерирует рекомендацию на основе стадии и метрик.

        Args:
            stage: Стадия оффера
            roi: ROI оффера
            roi_trend: Тренд ROI
            revenue_trend: Тренд дохода

        Returns:
            str: Рекомендация
        """
        recommendations = {
            "new": "Тестируйте объемы, собирайте статистику",
            "growing": "Масштабируйте осторожно, отслеживайте CR",
            "mature": "Поддерживайте текущий объем, ищите оптимизации",
            "declining": "Найдите причину падения, рассмотрите закрытие",
            "dead": "Закройте оффер, перераспределите бюджет"
        }

        base_recommendation = recommendations.get(stage, "Проверьте данные")

        # Добавляем детали для позитивных сценариев
        if stage == "growing" and roi > 50 and revenue_trend == "growing":
            return "Масштабируйте! ROI и объемы растут"
        elif stage == "mature" and roi > 100:
            return "Отличный результат! Поддерживайте, ищите возможности"
        elif stage == "declining" and roi_trend == "declining":
            return "Срочно: ROI падает, прекратите трафик"

        return base_recommendation

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций из результатов анализа.
        """
        recommendations = []
        offers = raw_data.get("offers", [])
        summary = raw_data.get("summary", {})

        # Рекомендация по мертвым офферам
        dead_offers = [x for x in offers if x["stage"] == "dead"]
        if dead_offers:
            dead_names = ', '.join([f"[{x['offer_id']}] {x['offer_name']}" for x in dead_offers[:3]])
            recommendations.append(
                f"Закройте {len(dead_offers)} мертвых офферов: {dead_names}"
            )

        # Рекомендация по растущим офферам
        growing_offers = [x for x in offers if x["stage"] == "growing" and x["roi"] > 20]
        if growing_offers:
            recommendations.append(
                f"Масштабируйте {len(growing_offers)} растущих офферов с положительным ROI"
            )

        # Рекомендация по общему портфелю
        if summary.get("avg_roi", 0) > 50:
            recommendations.append("Портфель в отличном состоянии - рассмотрите расширение бюджета")
        elif summary.get("avg_roi", 0) < 0:
            recommendations.append("Негативный средний ROI - срочно проверьте все офферы")

        return recommendations

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        offers = raw_data.get("offers", [])
        summary = raw_data.get("summary", {})

        charts = []

        # График распределения по стадиям
        stage_counts = {
            "new": summary.get("new_offers", 0),
            "growing": summary.get("growing_offers", 0),
            "mature": summary.get("mature_offers", 0),
            "declining": summary.get("declining_offers", 0),
            "dead": summary.get("dead_offers", 0)
        }

        stage_labels = {
            "new": "Новые",
            "growing": "Растущие",
            "mature": "Зрелые",
            "declining": "Умирающие",
            "dead": "Мертвые"
        }

        stage_colors = {
            "new": "rgba(23, 162, 184, 0.8)",      # Cyan
            "growing": "rgba(40, 167, 69, 0.8)",   # Green
            "mature": "rgba(13, 110, 253, 0.8)",   # Blue
            "declining": "rgba(255, 193, 7, 0.8)", # Yellow
            "dead": "rgba(220, 53, 69, 0.8)"       # Red
        }

        charts.append({
            "id": "lifecycle_stage_distribution",
            "type": "doughnut",
            "data": {
                "labels": [stage_labels[stage] for stage in ["new", "growing", "mature", "declining", "dead"]],
                "datasets": [{
                    "data": [stage_counts[stage] for stage in ["new", "growing", "mature", "declining", "dead"]],
                    "backgroundColor": [stage_colors[stage] for stage in ["new", "growing", "mature", "declining", "dead"]],
                    "borderColor": "rgba(255, 255, 255, 0.1)",
                    "borderWidth": 2
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение офферов по стадиям"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График ROI по офферам (top 10)
        top_offers = sorted(offers, key=lambda x: abs(x.get("roi", 0)), reverse=True)[:10]
        if top_offers:
            charts.append({
                "id": "lifecycle_roi_by_offer",
                "type": "bar",
                "data": {
                    "labels": [f"[{x['offer_id']}] {x['offer_name'][:20]}" for x in top_offers],
                    "datasets": [{
                        "label": "ROI (%)",
                        "data": [x.get("roi", 0) for x in top_offers],
                        "backgroundColor": [
                            "rgba(40, 167, 69, 0.8)" if x.get("roi", 0) > 0 else "rgba(220, 53, 69, 0.8)"
                            for x in top_offers
                        ],
                        "borderColor": [
                            "rgba(40, 167, 69, 1)" if x.get("roi", 0) > 0 else "rgba(220, 53, 69, 1)"
                            for x in top_offers
                        ],
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "indexAxis": "y",
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "ROI по топ офферам"
                        }
                    },
                    "scales": {
                        "x": {
                            "beginAtZero": True
                        }
                    }
                }
            })

        return charts
