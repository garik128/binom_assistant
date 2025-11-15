"""
Модуль ранжирования офферов по комплексной прибыльности (Offer Profitability Ranker)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict
import statistics

from storage.database.base import get_session
from storage.database.models import Offer, OfferStatsDaily
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


class OfferProfitabilityRanker(BaseModule):
    """
    Модуль ранжирования офферов по комплексной прибыльности.

    Ранжирует офферы (группы кампаний) на основе комбинированных метрик:
    - Средний ROI (вес 40%)
    - Объем прибыли (вес 30%)
    - Стабильность апрувов для CPA (вес 20%)
    - Потенциал масштабирования (вес 10%)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="offer_profitability_ranker",
            name="Рейтинг офферов",
            category="sources_offers",
            description="Ранжирует офферы по комплексной прибыльности",
            detailed_description="Модуль анализирует все офферы на основе данных из таблиц offers и offer_stats_daily. Выстраивает рейтинг на основе ROI, объема прибыли, стабильности апрувов и потенциала масштабирования. Помогает быстро определить наиболее перспективные офферы для инвестирования. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="high",
            tags=["offers", "profitability", "roi", "scaling", "ranking"]
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
                "min_cost": 10.0,  # минимум расход за период
                "min_roi_for_scaling": 30,  # минимальный ROI для масштабирования (%)
                "min_approval_rate": 20,  # минимальная норма апрува (%)
                "max_approval_rate": 80,  # максимальная норма апрува (%)
                "severity_weak_score": 40,  # порог для warning severity (слабые офферы)
                "severity_info_score": 50  # порог для info severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа офферов",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_cost": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход за период для фильтрации офферов",
                "type": "number",
                "min": 0,
                "max": 10000,
                "default": 10.0
            },
            "min_roi_for_scaling": {
                "label": "Минимальный ROI для масштабирования (%)",
                "description": "Минимальный ROI для рекомендации масштабирования оффера",
                "type": "number",
                "min": 0,
                "max": 200,
                "default": 30
            },
            "min_approval_rate": {
                "label": "Мин. норма апрува (%)",
                "description": "Минимальная здоровая норма апрува для оффера",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 20
            },
            "max_approval_rate": {
                "label": "Макс. норма апрува (%)",
                "description": "Максимальная здоровая норма апрува для оффера",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 80
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "score",
            "metric_label": "Score",
            "metric_unit": "",
            "description": "Пороги критичности на основе общего score оффера",
            "thresholds": {
                "severity_weak_score": {
                    "label": "Порог слабого оффера",
                    "description": "Score ниже этого значения считается слабым оффером (warning)",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 40
                },
                "severity_info_score": {
                    "label": "Порог информационного уровня",
                    "description": "Score выше этого значения - информационный уровень",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "warning", "label": "Предупреждение", "color": "#f59e0b", "condition": "score < weak_score"},
                {"value": "info", "label": "Инфо", "color": "#3b82f6", "condition": "score >= weak_score"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ прибыльности офферов.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о ранжировании офферов
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_cost = config.params.get("min_cost", 10.0)
        min_roi_for_scaling = config.params.get("min_roi_for_scaling", 30)
        min_approval_rate = config.params.get("min_approval_rate", 20)
        max_approval_rate = config.params.get("max_approval_rate", 80)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем данные по офферам с их статистикой
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
                "offer_id": None,
                "offer_name": None,
                "network_id": None,
                "geo": None,
                "payout": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "total_clicks": 0,
                "roi_values": [],
                "daily_roi_values_by_day": defaultdict(list),
                "daily_stats": [],
                "days_with_data": 0,
                "is_cpa": False  # признак CPA офера
            })

            for row in results:
                offer_id = row.id

                offers_data[offer_id]["offer_id"] = row.id
                offers_data[offer_id]["offer_name"] = row.name
                offers_data[offer_id]["network_id"] = row.network_id
                offers_data[offer_id]["geo"] = row.geo
                offers_data[offer_id]["payout"] = float(row.payout) if row.payout else 0

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                leads = float(row.leads) if row.leads else 0
                a_leads = float(row.a_leads) if row.a_leads else 0
                clicks = float(row.clicks) if row.clicks else 0

                offers_data[offer_id]["total_cost"] += cost
                offers_data[offer_id]["total_revenue"] += revenue
                offers_data[offer_id]["total_leads"] += leads
                offers_data[offer_id]["total_a_leads"] += a_leads
                offers_data[offer_id]["total_clicks"] += clicks

                if cost > 0:
                    offers_data[offer_id]["days_with_data"] += 1

                    # Рассчитываем дневной ROI
                    daily_roi = ((revenue - cost) / cost) * 100
                    offers_data[offer_id]["roi_values"].append(daily_roi)
                    offers_data[offer_id]["daily_roi_values_by_day"][row.date].append(daily_roi)

                offers_data[offer_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads,
                    "clicks": clicks
                })

                # Определение типа офера (CPA если есть approve_leads)
                if a_leads > 0:
                    offers_data[offer_id]["is_cpa"] = True

            # Анализ офферов
            ranked_offers = []

            for offer_id, offer_data in offers_data.items():
                # Пропускаем офферы с минимальным расходом
                if offer_data["total_cost"] < min_cost:
                    continue

                # Расчет ROI
                total_cost = offer_data["total_cost"]
                total_revenue = offer_data["total_revenue"]

                roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

                # Для расчета стабильности используем дневные данные
                daily_roi_values = []
                for daily_data in offer_data["daily_stats"]:
                    if daily_data["cost"] > 0:
                        daily_roi = ((daily_data["revenue"] - daily_data["cost"]) / daily_data["cost"]) * 100
                        daily_roi_values.append(daily_roi)

                # 1. Средний ROI (вес 40%)
                avg_roi_score = self._calculate_avg_roi_score(roi)

                # 2. Объем прибыли (вес 30%)
                profit_volume = total_revenue - total_cost
                profit_volume_score = self._calculate_profit_volume_score(profit_volume, offer_data["total_cost"])

                # 3. Стабильность апрувов для CPA (вес 20%)
                approval_stability_score = self._calculate_approval_stability_score(
                    offer_data,
                    offer_data["is_cpa"]
                )

                # 4. Потенциал масштабирования (вес 10%)
                scaling_potential_score = self._calculate_scaling_potential_score(
                    offer_data,
                    daily_roi_values
                )

                # Финальный рейтинг
                final_score = (
                    avg_roi_score * 0.40 +
                    profit_volume_score * 0.30 +
                    approval_stability_score * 0.20 +
                    scaling_potential_score * 0.10
                )

                ranked_offers.append({
                    "offer_id": offer_id,
                    "offer_name": offer_data["offer_name"],
                    "network_id": offer_data.get("network_id"),
                    "geo": offer_data.get("geo"),
                    "avg_roi": round(roi, 1),
                    "total_profit": round(profit_volume, 2),
                    "stability_score": round(approval_stability_score, 1),
                    "scaling_potential": round(scaling_potential_score, 1),
                    "final_score": round(final_score, 1),
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "is_cpa": offer_data["is_cpa"]
                })

            # Сортируем по финальному рейтингу
            ranked_offers.sort(key=lambda x: x["final_score"], reverse=True)

            # Добавляем ранги
            for idx, offer in enumerate(ranked_offers, 1):
                offer["rank"] = idx

            return {
                "offers": ranked_offers,
                "summary": {
                    "total_offers": len(ranked_offers),
                    "avg_roi_portfolio": round(statistics.mean([o["avg_roi"] for o in ranked_offers]), 1) if ranked_offers else 0,
                    "total_profit_portfolio": round(sum(o["total_profit"] for o in ranked_offers), 2),
                    "cpa_offers": sum(1 for o in ranked_offers if o["is_cpa"]),
                    "cpl_offers": sum(1 for o in ranked_offers if not o["is_cpa"])
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "thresholds": {
                    "severity_weak_score": config.params.get("severity_weak_score", 40),
                    "severity_info_score": config.params.get("severity_info_score", 50)
                }
            }

    def _calculate_avg_roi_score(self, roi: float) -> float:
        """
        Рассчитывает score для среднего ROI (0-100).

        Args:
            roi: ROI в процентах

        Returns:
            float: Score от 0 до 100
        """
        # Шкала преобразования:
        # -100% -> 0
        # 0% -> 50
        # 100% -> 100
        # 200% -> 100 (максимум)
        score = 50 + (roi / 2)
        score = max(0, min(100, score))
        return score

    def _calculate_profit_volume_score(self, profit: float, cost: float) -> float:
        """
        Рассчитывает score на основе объема прибыли.

        Чем больше абсолютная прибыль и ROI, тем выше score.

        Args:
            profit: Абсолютная прибыль ($)
            cost: Общий расход ($)

        Returns:
            float: Score от 0 до 100
        """
        if cost == 0:
            return 50

        roi = (profit / cost) * 100 if cost > 0 else 0

        # Если убыток - низкий score
        if profit < 0:
            return max(0, 50 + (roi / 2))

        # Для прибыли: ROI 50% = 75, ROI 100% = 100
        # Базовый score за объем + бонус за эффективность
        volume_score = min(50, (profit / 100))  # $100 = 50 points
        roi_bonus = (roi / 2) if roi > 0 else 0

        score = min(100, 50 + volume_score + (roi_bonus / 2))
        return score

    def _calculate_approval_stability_score(self, offer_data: Dict[str, Any], is_cpa: bool) -> float:
        """
        Рассчитывает стабильность апрувов (критерий для CPA).

        Args:
            offer_data: Данные офера
            is_cpa: Является ли оффер CPA

        Returns:
            float: Score от 0 до 100
        """
        # Если это CPL, стабильность не критична
        if not is_cpa:
            return 75  # Нейтральное значение для CPL

        # Для CPA анализируем стабильность approval rate
        total_approved = offer_data["total_a_leads"]
        total_leads = offer_data["total_leads"]

        if total_leads == 0:
            return 50

        approval_rate = (total_approved / total_leads) * 100

        # Анализируем волатильность approval rate по дням
        daily_approval_rates = []
        for daily_data in offer_data["daily_stats"]:
            if daily_data["leads"] > 0:
                daily_rate = (daily_data["a_leads"] / daily_data["leads"]) * 100
                daily_approval_rates.append(daily_rate)

        # Простая метрика: стабильность на основе ratio approved/leads
        # Идеальная стабильность: 20-80% approval rate
        # Слишком низкая или высокая - менее стабильна

        if approval_rate >= 20 and approval_rate <= 80:
            stability = 100 - abs(50 - approval_rate)
        else:
            stability = max(0, 100 - (abs(50 - approval_rate) * 2))

        return stability

    def _calculate_scaling_potential_score(self, offer_data: Dict[str, Any], daily_roi_values: List[float]) -> float:
        """
        Рассчитывает потенциал масштабирования офера.

        Факторы:
        - Количество дней с данными (больше = стабильнее)
        - Консистентность ROI (меньше волатильность = лучше масштабируется)
        - Наличие margin'а (ROI > 30%)

        Args:
            offer_data: Данные офера
            daily_roi_values: ROI значения по дням

        Returns:
            float: Score от 0 до 100
        """
        days_count = len([d for d in offer_data["daily_stats"] if d["cost"] > 0])

        # Количество дней влияет на масштабируемость
        days_count_score = min(100, days_count * 10)

        # Консистентность (низкая волатильность)
        if len(daily_roi_values) > 1:
            try:
                mean_roi = statistics.mean(daily_roi_values)
                stdev_roi = statistics.stdev(daily_roi_values)

                cv = stdev_roi / abs(mean_roi) if abs(mean_roi) > 0 else stdev_roi
                consistency_score = max(0, 100 * (1 - cv))
            except Exception:
                consistency_score = 50
        else:
            consistency_score = 50 if days_count_score > 0 else 0

        # Margin (должен быть > 30%)
        avg_roi = offer_data["total_revenue"] / offer_data["total_cost"] * 100 - 100 if offer_data["total_cost"] > 0 else 0
        margin_score = min(100, max(0, avg_roi / 1.5)) if avg_roi > 30 else min(50, max(0, avg_roi / 1.5))

        # Комбинируем: 50% консистентность, 30% количество дней, 20% margin
        scaling_score = (
            consistency_score * 0.50 +
            days_count_score * 0.30 +
            margin_score * 0.20
        )

        return scaling_score

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО для этого модуля.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        offers = raw_data.get("offers", [])

        if not offers:
            return []

        charts = []

        # График рейтинга офферов
        top_offers = offers[:10]  # Топ 10 офферов

        charts.append({
            "id": "offer_ranking_chart",
            "type": "bar",
            "data": {
                "labels": [f"[{o['offer_id']}] {o['offer_name'][:30]}" for o in top_offers],
                "datasets": [
                    {
                        "label": "ROI (%)",
                        "data": [o["avg_roi"] for o in top_offers],
                        "backgroundColor": "rgba(13, 110, 253, 0.6)",
                        "borderColor": "rgba(13, 110, 253, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "Score",
                        "data": [o["final_score"] for o in top_offers],
                        "backgroundColor": "rgba(40, 167, 69, 0.6)",
                        "borderColor": "rgba(40, 167, 69, 1)",
                        "borderWidth": 1
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ офферы по рейтингу"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Значение"
                        }
                    }
                }
            }
        })

        # Лепестковая диаграмма компонентов top 3 офферов
        if len(top_offers) >= 1:
            top_3 = top_offers[:3]
            charts.append({
                "id": "offer_components_radar",
                "type": "radar",
                "data": {
                    "labels": [
                        "ROI Score",
                        "Прибыль",
                        "Стабильность",
                        "Масштабируемость"
                    ],
                    "datasets": [
                        {
                            "label": f"[{top_3[i]['offer_id']}] {top_3[i]['offer_name'][:20]}",
                            "data": [
                                self._calculate_avg_roi_score(top_3[i]["avg_roi"]),
                                self._calculate_profit_volume_score(top_3[i]["total_profit"], top_3[i]["total_cost"]),
                                top_3[i]["stability_score"],
                                top_3[i]["scaling_potential"]
                            ],
                            "borderColor": ["rgba(13, 110, 253, 1)", "rgba(40, 167, 69, 1)", "rgba(255, 193, 7, 1)"][i],
                            "backgroundColor": ["rgba(13, 110, 253, 0.2)", "rgba(40, 167, 69, 0.2)", "rgba(255, 193, 7, 0.2)"][i]
                        }
                        for i in range(min(3, len(top_3)))
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Компоненты оценки (Топ 3)"
                        }
                    },
                    "scales": {
                        "r": {
                            "beginAtZero": True,
                            "max": 100
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов по офферам.
        """
        offers = raw_data.get("offers", [])
        summary = raw_data.get("summary", {})
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        if not offers:
            return alerts

        # Получаем настраиваемые пороги severity
        severity_weak_score = thresholds.get("severity_weak_score", 40)

        # Основной алерт с рейтингом
        message = f"Проанализировано офферов: {summary.get('total_offers', 0)}\n"
        message += f"Средний ROI портфеля: {summary.get('avg_roi_portfolio', 0):.1f}%\n"
        message += f"Общая прибыль: ${summary.get('total_profit_portfolio', 0):.2f}\n"
        message += f"CPA: {summary.get('cpa_offers', 0)} / CPL: {summary.get('cpl_offers', 0)}\n\n"

        message += "Топ офферы:\n"
        for offer in offers[:5]:
            status = "[OK]" if offer["final_score"] >= 70 else "[MED]" if offer["final_score"] >= 50 else "[LOW]"
            message += f"{status} [{offer['offer_id']}] {offer['offer_name']}: {offer['final_score']:.1f} (ROI {offer['avg_roi']:.1f}%)\n"

        alerts.append({
            "type": "offer_ranking",
            "severity": "info",
            "message": message,
            "top_offer": f"[{offers[0]['offer_id']}] {offers[0]['offer_name']}" if offers else None,
            "top_offer_score": offers[0]["final_score"] if offers else 0,
            "total_offers": summary.get("total_offers", 0)
        })

        # Алерты на слабые офферы с настраиваемым порогом
        weak_offers = [o for o in offers if o["final_score"] < severity_weak_score]
        if weak_offers:
            alerts.append({
                "type": "weak_offers",
                "severity": "warning",
                "message": f"Обнаружено {len(weak_offers)} офферов с низким рейтингом (score < {severity_weak_score})",
                "weak_offers_count": len(weak_offers),
                "threshold": severity_weak_score
            })

        return alerts
