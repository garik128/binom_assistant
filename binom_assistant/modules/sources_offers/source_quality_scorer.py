"""
Модуль оценки качества источников трафика (Source Quality Scorer)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from contextlib import contextmanager
from collections import defaultdict
import statistics

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


class SourceQualityScorer(BaseModule):
    """
    Модуль оценки качества источников трафика (Source Quality Scorer).

    Анализирует качество источников трафика на основе:
    - Средний CR по источнику (25%)
    - Качество лидов - approve rate для CPA (25%)
    - Стабильность поставки трафика (25%)
    - Стоимость трафика - CPC (25%)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="source_quality_scorer",
            name="Качество источников",
            category="sources_offers",
            description="Оценивает качество источников трафика",
            detailed_description="Модуль анализирует качество источников трафика на основе среднего CR, approve rate, стабильности и CPC. Формирует рейтинг источников от 'poor' до 'excellent'. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="medium",
            tags=["sources", "quality", "cr", "approve_rate", "stability", "cpc"]
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
                "min_clicks": 100,  # минимум кликов
                "excellent_threshold": 80,  # порог отличного качества
                "good_threshold": 60,  # порог хорошего качества
                "poor_threshold": 40,  # порог низкого качества
                "unstable_threshold": 50,  # порог нестабильности
                "severity_poor_quality": 40,  # порог для warning severity (плохие источники)
                "severity_unstable": 50  # порог для info severity (нестабильные источники)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа источников",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов для включения источника в анализ",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 100
            },
            "excellent_threshold": {
                "label": "Порог отличного качества",
                "description": "Минимальный score для отличного качества источника",
                "type": "number",
                "min": 50,
                "max": 100,
                "default": 80
            },
            "good_threshold": {
                "label": "Порог хорошего качества",
                "description": "Минимальный score для хорошего качества источника",
                "type": "number",
                "min": 30,
                "max": 100,
                "default": 60
            },
            "poor_threshold": {
                "label": "Порог низкого качества",
                "description": "Минимальный score для удовлетворительного качества",
                "type": "number",
                "min": 10,
                "max": 100,
                "default": 40
            },
            "unstable_threshold": {
                "label": "Порог нестабильности",
                "description": "Минимальный score стабильности для стабильных источников",
                "type": "number",
                "min": 10,
                "max": 100,
                "default": 50
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "quality_score",
            "metric_label": "Quality Score",
            "metric_unit": "",
            "description": "Пороги критичности на основе качественного индекса источника",
            "thresholds": {
                "severity_poor_quality": {
                    "label": "Порог плохого качества",
                    "description": "Quality score ниже этого значения - плохой источник (warning)",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 40
                },
                "severity_unstable": {
                    "label": "Порог нестабильности",
                    "description": "Stability score ниже этого значения - нестабильный источник (info)",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "warning", "label": "Предупреждение", "color": "#f59e0b", "condition": "quality_score < poor_quality"},
                {"value": "info", "label": "Инфо", "color": "#3b82f6", "condition": "stability_score < unstable"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ качества источников.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о качестве источников
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_clicks = config.params.get("min_clicks", 100)
        excellent_threshold = config.params.get("excellent_threshold", 80)
        good_threshold = config.params.get("good_threshold", 60)
        poor_threshold = config.params.get("poor_threshold", 40)
        unstable_threshold = config.params.get("unstable_threshold", 50)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.ts_name,  # Traffic Source Name
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.a_leads,
                CampaignStatsDaily.cr,
                CampaignStatsDaily.approve,
                CampaignStatsDaily.cpc
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from
            ).order_by(
                Campaign.ts_name,
                CampaignStatsDaily.date
            )

            results = query.all()

            # Группировка по источникам
            sources_data = defaultdict(lambda: {
                "campaigns": [],
                "total_clicks": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "cr_values": [],
                "approve_values": [],
                "cpc_values": [],
                "daily_clicks_count": 0,
                "days_with_data": 0
            })

            for row in results:
                source = row.ts_name or "Неизвестен"

                # Преобразование значений
                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                clicks = int(row.clicks) if row.clicks else 0
                leads = int(row.leads) if row.leads else 0
                a_leads = int(row.a_leads) if row.a_leads else 0
                cr = float(row.cr) if row.cr else 0
                approve = float(row.approve) if row.approve else 0
                cpc = float(row.cpc) if row.cpc else 0

                sources_data[source]["total_clicks"] += clicks
                sources_data[source]["total_leads"] += leads
                sources_data[source]["total_a_leads"] += a_leads
                sources_data[source]["total_cost"] += cost
                sources_data[source]["total_revenue"] += revenue

                # Сбор значений для расчета средних
                if clicks > 0:
                    sources_data[source]["daily_clicks_count"] += 1
                    sources_data[source]["cr_values"].append(cr)
                    sources_data[source]["cpc_values"].append(cpc)

                if a_leads > 0 or leads > 0:
                    sources_data[source]["approve_values"].append(approve)

                # Отслеживание уникальных кампаний и дней
                if clicks > 0:
                    sources_data[source]["days_with_data"] += 1

                # Добавляем информацию о кампании
                if row.binom_id not in [c["binom_id"] for c in sources_data[source]["campaigns"]]:
                    sources_data[source]["campaigns"].append({
                        "binom_id": row.binom_id,
                        "name": row.current_name
                    })

            # Анализ каждого источника
            sources_list = []

            for source, data in sources_data.items():
                # Пропускаем источники с малым количеством кликов
                if data["total_clicks"] < min_clicks:
                    continue

                # Расчет метрик
                avg_cr = statistics.mean(data["cr_values"]) if data["cr_values"] else 0
                avg_approve_rate = statistics.mean(data["approve_values"]) if data["approve_values"] else 0
                avg_cpc = statistics.mean(data["cpc_values"]) if data["cpc_values"] else 0

                # Стабильность: по количеству дней с данными vs общего периода
                # Лучше = когда источник работает стабильно все дни
                if data["days_with_data"] > 0:
                    stability_score = (data["days_with_data"] / days) * 100
                else:
                    stability_score = 0

                # Средний CPC (ниже = лучше)
                # Нормализуем: 0.01$ = 100 баллов, 0.10$ и выше = 0 баллов
                # Линейное масштабирование для согласованности
                if avg_cpc <= 0.01:
                    cpc_score = 100
                elif avg_cpc >= 0.10:
                    cpc_score = 0
                else:
                    # Линейная интерполяция между 0.01$ (100 баллов) и 0.10$ (0 баллов)
                    cpc_score = 100 - ((avg_cpc - 0.01) / 0.09) * 100

                # Нормализуем CR к шкале 0-100
                # Предполагаем, что максимальный хороший CR = 20% для нормализации
                cr_score = min(100, (avg_cr / 20) * 100)

                # Рассчитываем общий качественный индекс (0-100)
                # Все компоненты теперь в шкале 0-100
                quality_score = (
                    cr_score * 0.25 +          # CR весит 25% (нормализован к 0-100)
                    avg_approve_rate * 0.25 +  # Approve rate весит 25%
                    stability_score * 0.25 +   # Стабильность весит 25%
                    cpc_score * 0.25           # CPC весит 25%
                )

                # Определяем рейтинг
                if quality_score >= 80:
                    rating = "excellent"
                elif quality_score >= 60:
                    rating = "good"
                elif quality_score >= 40:
                    rating = "medium"
                else:
                    rating = "poor"

                sources_list.append({
                    "source": source,
                    "avg_cr": round(avg_cr, 2),
                    "cr_score": round(cr_score, 1),  # Нормализованный балл CR для прозрачности
                    "approve_rate": round(avg_approve_rate, 2),
                    "stability_score": round(stability_score, 2),
                    "avg_cpc": round(avg_cpc, 4),
                    "cpc_score": round(cpc_score, 1),  # Балл CPC для прозрачности
                    "quality_score": round(quality_score, 1),
                    "rating": rating,
                    "total_clicks": data["total_clicks"],
                    "total_leads": data["total_leads"],
                    "total_a_leads": data["total_a_leads"],
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "campaigns_count": len(data["campaigns"])
                })

            # Сортируем по качественному индексу
            sources_list.sort(key=lambda x: x["quality_score"], reverse=True)

            return {
                "sources": sources_list,
                "summary": {
                    "total_sources": len(sources_list),
                    "excellent_count": len([s for s in sources_list if s["rating"] == "excellent"]),
                    "good_count": len([s for s in sources_list if s["rating"] == "good"]),
                    "medium_count": len([s for s in sources_list if s["rating"] == "medium"]),
                    "poor_count": len([s for s in sources_list if s["rating"] == "poor"]),
                    "avg_quality": round(statistics.mean([s["quality_score"] for s in sources_list]), 1) if sources_list else 0
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "thresholds": {
                    "severity_poor_quality": config.params.get("severity_poor_quality", 40),
                    "severity_unstable": config.params.get("severity_unstable", 50)
                }
            }

    def format_results(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Форматирование результатов для UI.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            Dict[str, Any]: Отформатированные данные
        """
        return raw_data

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        sources = raw_data.get("sources", [])
        summary = raw_data.get("summary", {})

        charts = []

        # График распределения источников по рейтингам
        if summary.get("total_sources", 0) > 0:
            charts.append({
                "id": "source_quality_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Excellent", "Good", "Medium", "Poor"],
                    "datasets": [{
                        "data": [
                            summary.get("excellent_count", 0),
                            summary.get("good_count", 0),
                            summary.get("medium_count", 0),
                            summary.get("poor_count", 0)
                        ],
                        "backgroundColor": [
                            "rgba(40, 167, 69, 0.8)",  # green
                            "rgba(23, 162, 184, 0.8)",  # cyan
                            "rgba(255, 193, 7, 0.8)",   # yellow
                            "rgba(220, 53, 69, 0.8)"    # red
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение источников по качеству"
                        },
                        "legend": {
                            "position": "bottom"
                        }
                    }
                }
            })

        # График качественного индекса для топ источников
        if sources:
            top_sources = sources[:10]
            charts.append({
                "id": "source_quality_scores",
                "type": "bar",
                "data": {
                    "labels": [s["source"] for s in top_sources],
                    "datasets": [{
                        "label": "Качественный индекс",
                        "data": [s["quality_score"] for s in top_sources],
                        "backgroundColor": [
                            "rgba(40, 167, 69, 0.8)" if s["rating"] == "excellent" else
                            "rgba(23, 162, 184, 0.8)" if s["rating"] == "good" else
                            "rgba(255, 193, 7, 0.8)" if s["rating"] == "medium" else
                            "rgba(220, 53, 69, 0.8)"
                            for s in top_sources
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ 10 источников по качеству"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "max": 100
                        }
                    }
                }
            })

        return charts

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций на основе анализа.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            List[str]: Список рекомендаций
        """
        sources = raw_data.get("sources", [])
        summary = raw_data.get("summary", {})
        recommendations = []

        # Рекомендации по плохим источникам
        poor_sources = [s for s in sources if s["rating"] == "poor"]
        if poor_sources:
            recommendations.append(
                f"Рассмотрите отключение или переработку стратегии для {len(poor_sources)} источников "
                f"с низким качеством: {', '.join([s['source'] for s in poor_sources[:3]])}"
            )

        # Рекомендации по хорошим источникам
        excellent_sources = [s for s in sources if s["rating"] == "excellent"]
        if excellent_sources:
            recommendations.append(
                f"Увеличьте инвестиции в топ-качественные источники: "
                f"{', '.join([s['source'] for s in excellent_sources[:3]])}"
            )

        # Рекомендация по стабильности
        unstable_sources = [s for s in sources if s["stability_score"] < 50]
        if unstable_sources:
            recommendations.append(
                f"Некоторые источники работают нестабильно. Проверьте {len(unstable_sources)} источников "
                f"с низкой стабильностью поставки"
            )

        # Рекомендация по CPC
        expensive_sources = [s for s in sources if s["avg_cpc"] > 0.1]
        if expensive_sources:
            recommendations.append(
                f"Высокая стоимость трафика у {len(expensive_sources)} источников. "
                f"Рассмотрите переговоры или поиск альтернатив"
            )

        if not recommendations:
            recommendations.append("Качество источников в целом хорошее. Продолжайте мониторинг.")

        return recommendations

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов.

        Args:
            raw_data: Сырые данные из analyze()

        Returns:
            List[Dict[str, Any]]: Список алертов
        """
        sources = raw_data.get("sources", [])
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        # Получаем настраиваемые пороги severity
        severity_poor_quality = thresholds.get("severity_poor_quality", 40)
        severity_unstable = thresholds.get("severity_unstable", 50)

        # Алерт о плохих источниках с настраиваемым порогом
        poor_sources = [s for s in sources if s["quality_score"] < severity_poor_quality]
        if poor_sources:
            alerts.append({
                "type": "poor_source_quality",
                "severity": "warning",
                "message": f"Выявлено {len(poor_sources)} источников с низким качеством (score < {severity_poor_quality})",
                "affected_sources": [s["source"] for s in poor_sources[:5]],
                "recommended_action": "Пересмотрите стратегию для этих источников или отключите их",
                "threshold": severity_poor_quality
            })

        # Алерт о нестабильных источниках с настраиваемым порогом
        unstable_sources = [s for s in sources if s["stability_score"] < severity_unstable]
        if unstable_sources:
            alerts.append({
                "type": "unstable_source",
                "severity": "info",
                "message": f"{len(unstable_sources)} источников показывают нестабильную поставку (stability < {severity_unstable})",
                "affected_sources": [s["source"] for s in unstable_sources[:5]],
                "recommended_action": "Проверьте конфигурацию и соединение с источниками",
                "threshold": severity_unstable
            })

        return alerts
