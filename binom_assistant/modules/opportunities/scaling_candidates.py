"""
Модуль поиска кандидатов для масштабирования (Scaling Candidates)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
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


class ScalingCandidates(BaseModule):
    """
    Детектор кандидатов для масштабирования (Scaling Candidates).

    Находит стабильные прибыльные кампании, готовые к масштабированию:
    - ROI > roi_threshold в течение всего периода
    - Минимальный расход > min_daily_spend
    - Низкая волатильность: CV < volatility_threshold
    - CPC не растет (рост < cpc_growth_limit)

    Критерии:
    - ROI >= roi_threshold (по умолчанию 50%) в течение всего периода
    - Минимальный расход > min_daily_spend (по умолчанию $1/день)
    - Низкая волатильность: CV < volatility_threshold (по умолчанию 0.3)
    - Рост CPC < cpc_growth_limit (по умолчанию 20%)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="scaling_candidates",
            name="Готовы к росту",
            category="opportunities",
            description="Выявляет стабильные прибыльные кампании, готовые к масштабированию",
            detailed_description="Модуль находит кампании с высоким стабильным ROI, низкой волатильностью и отсутствием признаков выгорания. Помогает выявить безопасные направления для масштабирования.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["opportunities", "scaling", "roi", "stability"]
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
                "days": 14,  # период для анализа
                "roi_threshold": 50,  # минимальный ROI (%)
                "min_daily_spend": 1.0,  # минимальный расход в день ($)
                "volatility_threshold": 0.3,  # максимальный CV для волатильности
                "cpc_growth_limit": 20  # максимальный рост CPC (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа кампаний",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "roi_threshold": {
                "label": "Минимальный ROI (%)",
                "description": "Минимальный ROI для включения в список",
                "type": "number",
                "min": 20,
                "max": 200,
                "default": 50
            },
            "min_daily_spend": {
                "label": "Минимальный расход в день ($)",
                "description": "Минимальный средний расход для включения в анализ",
                "type": "number",
                "min": 0.5,
                "max": 10000,
                "default": 1.0
            },
            "volatility_threshold": {
                "label": "Порог волатильности",
                "description": "Максимальный коэффициент вариации ROI (0.3 = 30%)",
                "type": "number",
                "min": 0.1,
                "max": 1.0,
                "default": 0.3
            },
            "cpc_growth_limit": {
                "label": "Максимальный рост CPC (%)",
                "description": "Максимально допустимый рост CPC для определения отсутствия выгорания",
                "type": "number",
                "min": 10,
                "max": 50,
                "default": 20
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ кандидатов для масштабирования.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кандидатах для масштабирования
        """
        # Получение параметров
        days = config.params.get("days", 14)
        roi_threshold = config.params.get("roi_threshold", 50)
        min_daily_spend = config.params.get("min_daily_spend", 1.0)
        volatility_threshold = config.params.get("volatility_threshold", 0.3)
        cpc_growth_limit = config.params.get("cpc_growth_limit", 20)

        # Период анализа
        date_from = datetime.now().date() - timedelta(days=days - 1)
        # Дата разделения периода на первую и вторую половину
        half_days = days // 2
        split_date = datetime.now().date() - timedelta(days=half_days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue
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
                "total_cost": 0,
                "total_revenue": 0,
                "total_clicks": 0,
                "daily_stats": [],
                "first_half": {"cost": 0, "clicks": 0},
                "second_half": {"cost": 0, "clicks": 0},
                "days_with_data": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                clicks = row.clicks or 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_revenue"] += revenue
                campaigns_data[campaign_id]["total_clicks"] += clicks

                # Считаем дни с данными (расход > 0)
                if cost > 0:
                    campaigns_data[campaign_id]["days_with_data"] += 1

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "clicks": clicks
                })

                # Разделяем на первую и вторую половину для расчета CPC
                if row.date < split_date:
                    campaigns_data[campaign_id]["first_half"]["cost"] += cost
                    campaigns_data[campaign_id]["first_half"]["clicks"] += clicks
                else:
                    campaigns_data[campaign_id]["second_half"]["cost"] += cost
                    campaigns_data[campaign_id]["second_half"]["clicks"] += clicks

            # Обработка и поиск кандидатов
            scaling_candidates = []
            total_campaigns_checked = 0
            total_roi_sum = 0

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                # Расчет средних дневных метрик
                avg_daily_spend = data["total_cost"] / data["days_with_data"]

                # Фильтрация: минимальный расход
                if avg_daily_spend < min_daily_spend:
                    continue

                # Фильтрация: должен быть хотя бы минимальный расход
                if data["total_cost"] < min_daily_spend:
                    continue

                total_campaigns_checked += 1

                # Расчет дневных ROI для анализа волатильности
                daily_roi_values = []
                for day_stat in data["daily_stats"]:
                    if day_stat["cost"] > 0:
                        roi = ((day_stat["revenue"] - day_stat["cost"]) / day_stat["cost"]) * 100
                        daily_roi_values.append(roi)

                # Нужно минимум 3 дня с данными для статистической значимости
                if len(daily_roi_values) < 3:
                    continue

                # Расчет статистики ROI
                avg_roi = statistics.mean(daily_roi_values)
                min_roi = min(daily_roi_values)

                # Фильтрация: средний ROI должен быть >= roi_threshold
                if avg_roi < roi_threshold:
                    continue

                # Фильтрация: минимальный ROI тоже должен быть >= roi_threshold
                if min_roi < roi_threshold:
                    continue

                # Расчет волатильности (коэффициент вариации)
                # CV = std_dev / mean
                # CV корректен только для положительных средних значений
                if avg_roi > 0:
                    roi_volatility = statistics.stdev(daily_roi_values) / avg_roi
                else:
                    # Если средний ROI <= 0, пропускаем кампанию (не интересна для scaling)
                    continue

                # Фильтрация: волатильность должна быть приемлемой
                if roi_volatility > volatility_threshold:
                    continue

                # Расчет CPC для первой и второй половины периода
                first_half = data["first_half"]
                second_half = data["second_half"]

                # CPC первой половины
                if first_half["clicks"] > 0:
                    cpc_first_half = first_half["cost"] / first_half["clicks"]
                else:
                    cpc_first_half = 0

                # CPC второй половины
                if second_half["clicks"] > 0:
                    cpc_second_half = second_half["cost"] / second_half["clicks"]
                else:
                    cpc_second_half = 0

                # Расчет роста CPC
                if cpc_first_half > 0:
                    cpc_growth_percent = ((cpc_second_half - cpc_first_half) / cpc_first_half) * 100
                else:
                    # Если в первой половине не было кликов, но во второй есть
                    if cpc_second_half > 0:
                        cpc_growth_percent = 100  # Условно 100% рост
                    else:
                        cpc_growth_percent = 0

                # Фильтрация: рост CPC не должен превышать лимит
                if cpc_growth_percent > cpc_growth_limit:
                    continue

                # Расчет readiness_score
                # Формула: 100 - (roi_volatility * 100) - (cpc_growth * 0.5) - max(0, (50 - min_roi))
                readiness_score = 100 - (roi_volatility * 100) - (cpc_growth_percent * 0.5) - max(0, (50 - min_roi))
                readiness_score = max(0, min(100, readiness_score))  # Ограничиваем 0-100

                total_roi_sum += avg_roi

                scaling_candidates.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "avg_roi": round(avg_roi, 1),
                    "min_roi": round(min_roi, 1),
                    "roi_volatility": round(roi_volatility, 2),
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "cpc_first_half": round(cpc_first_half, 4),
                    "cpc_second_half": round(cpc_second_half, 4),
                    "cpc_growth_percent": round(cpc_growth_percent, 1),
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "readiness_score": round(readiness_score, 1)
                })

            # Сортировка: по readiness_score DESC
            scaling_candidates.sort(key=lambda x: -x["readiness_score"])

            return {
                "campaigns": scaling_candidates,
                "summary": {
                    "total_candidates": len(scaling_candidates),
                    "avg_roi": round(total_roi_sum / len(scaling_candidates), 1) if scaling_candidates else 0,
                    "avg_readiness_score": round(
                        sum(c["readiness_score"] for c in scaling_candidates) / len(scaling_candidates), 1
                    ) if scaling_candidates else 0,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "roi_threshold": roi_threshold,
                    "min_daily_spend": min_daily_spend,
                    "volatility_threshold": volatility_threshold,
                    "cpc_growth_limit": cpc_growth_limit
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        candidates = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})

        if not candidates:
            return []

        charts = []

        # График распределения по readiness_score
        # Группируем по диапазонам: 90-100, 80-90, 70-80, <70
        score_ranges = {"90-100": 0, "80-90": 0, "70-80": 0, "<70": 0}
        for c in candidates:
            score = c["readiness_score"]
            if score >= 90:
                score_ranges["90-100"] += 1
            elif score >= 80:
                score_ranges["80-90"] += 1
            elif score >= 70:
                score_ranges["70-80"] += 1
            else:
                score_ranges["<70"] += 1

        charts.append({
            "id": "candidates_readiness_chart",
            "type": "pie",
            "data": {
                "labels": ["90-100 (высокая)", "80-90 (хорошая)", "70-80 (средняя)", "<70 (низкая)"],
                "datasets": [{
                    "data": [
                        score_ranges["90-100"],
                        score_ranges["80-90"],
                        score_ranges["70-80"],
                        score_ranges["<70"]
                    ],
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.8)",
                        "rgba(23, 162, 184, 0.8)",
                        "rgba(255, 193, 7, 0.8)",
                        "rgba(220, 53, 69, 0.8)"
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение по готовности к масштабированию"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График readiness_score для топ-10
        top_10 = candidates[:10]
        charts.append({
            "id": "candidates_score_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Готовность к масштабированию (score)",
                    "data": [c["readiness_score"] for c in top_10],
                    "backgroundColor": "rgba(40, 167, 69, 0.6)",
                    "borderColor": "rgba(40, 167, 69, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по готовности к масштабированию"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 100,
                        "title": {
                            "display": True,
                            "text": "Готовность (0-100)"
                        }
                    }
                }
            }
        })

        # График ROI и волатильности для топ-10
        charts.append({
            "id": "candidates_roi_volatility_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "Средний ROI (%)",
                        "data": [c["avg_roi"] for c in top_10],
                        "backgroundColor": "rgba(40, 167, 69, 0.6)",
                        "borderColor": "rgba(40, 167, 69, 1)",
                        "borderWidth": 1,
                        "yAxisID": "y"
                    },
                    {
                        "label": "Волатильность (CV)",
                        "data": [c["roi_volatility"] * 100 for c in top_10],  # Конвертируем в проценты
                        "backgroundColor": "rgba(23, 162, 184, 0.6)",
                        "borderColor": "rgba(23, 162, 184, 1)",
                        "borderWidth": 1,
                        "yAxisID": "y1"
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10: ROI и волатильность"
                    }
                },
                "scales": {
                    "y": {
                        "type": "linear",
                        "display": True,
                        "position": "left",
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        }
                    },
                    "y1": {
                        "type": "linear",
                        "display": True,
                        "position": "right",
                        "title": {
                            "display": True,
                            "text": "Волатильность (%)"
                        },
                        "grid": {
                            "drawOnChartArea": False
                        }
                    }
                }
            }
        })

        # График роста CPC для топ-10
        charts.append({
            "id": "candidates_cpc_growth_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Рост CPC (%)",
                    "data": [c["cpc_growth_percent"] for c in top_10],
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.6)" if c["cpc_growth_percent"] < 10 else
                        "rgba(255, 193, 7, 0.6)" if c["cpc_growth_percent"] < 15 else
                        "rgba(220, 53, 69, 0.6)"
                        for c in top_10
                    ],
                    "borderColor": [
                        "rgba(40, 167, 69, 1)" if c["cpc_growth_percent"] < 10 else
                        "rgba(255, 193, 7, 1)" if c["cpc_growth_percent"] < 15 else
                        "rgba(220, 53, 69, 1)"
                        for c in top_10
                    ],
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10: рост CPC (признак выгорания)"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Рост CPC (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кандидатов на масштабирование.
        """
        candidates = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not candidates:
            return alerts

        # Общий алерт с краткой сводкой
        total_candidates = summary.get("total_candidates", 0)
        avg_roi = summary.get("avg_roi", 0)
        avg_readiness_score = summary.get("avg_readiness_score", 0)

        message = f"Найдено {total_candidates} кандидатов для масштабирования\n\n"
        message += f"Средний ROI: {avg_roi:.1f}%\n"
        message += f"Средняя готовность: {avg_readiness_score:.1f}/100\n\n"

        # Топ-5 кандидатов с высокой готовностью (score >= 90)
        top_candidates = [c for c in candidates if c["readiness_score"] >= 90]
        if top_candidates:
            message += f"Топ-кандидаты (готовность >= 90, {len(top_candidates)} кампаний):\n"
            for i, campaign in enumerate(top_candidates[:5], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['avg_roi']:.1f}%, "
                message += f"готовность {campaign['readiness_score']:.1f}, "
                message += f"${campaign['avg_daily_spend']:.2f}/день, "
                message += f"CPC рост {campaign['cpc_growth_percent']:.1f}%\n"

        # Кандидаты с хорошей готовностью (80 <= score < 90)
        good_candidates = [c for c in candidates if 80 <= c["readiness_score"] < 90]
        if good_candidates:
            message += f"\nХорошие кандидаты (готовность 80-90, {len(good_candidates)} кампаний):\n"
            for i, campaign in enumerate(good_candidates[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['avg_roi']:.1f}%, "
                message += f"готовность {campaign['readiness_score']:.1f}, "
                message += f"${campaign['avg_daily_spend']:.2f}/день\n"

        severity = "medium"  # Это возможности, а не проблемы

        alerts.append({
            "type": "scaling_candidates",
            "severity": severity,
            "message": message,
            "recommended_action": "Рассмотрите возможность постепенного увеличения бюджетов для топ-кандидатов. Начните с увеличения на 20-30%, отслеживая сохранение ROI и отсутствие роста CPC",
            "total_candidates": total_candidates,
            "avg_roi": round(avg_roi, 1),
            "avg_readiness_score": round(avg_readiness_score, 1),
            "top_count": len(top_candidates),
            "good_count": len(good_candidates)
        })

        return alerts
