"""
Модуль поиска скрытых точек роста (Hidden Gems Finder)
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


class HiddenGemsFinder(BaseModule):
    """
    Детектор скрытых точек роста (Hidden Gems).

    Находит недооцененные кампании с потенциалом роста:
    - Стабильно высокий ROI
    - Низкий текущий расход
    - Низкая волатильность

    Критерии:
    - ROI стабильно > roi_threshold (по умолчанию 30%)
    - Текущий средний расход < max_daily_spend (по умолчанию $5/день)
    - Минимальный расход > min_daily_spend (по умолчанию $1/день)
    - Низкая волатильность: CV (коэффициент вариации) < 0.3
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="hidden_gems_finder",
            name="Скрытые точки роста",
            category="opportunities",
            description="Находит недооцененные кампании с потенциалом роста",
            detailed_description="Модуль находит кампании с высоким стабильным ROI и низким текущим расходом. Помогает выявить перспективные направления для масштабирования.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["opportunities", "growth", "roi", "scaling"]
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
                "roi_threshold": 30,  # минимальный ROI (%)
                "max_daily_spend": 5.0,  # максимальный расход в день ($)
                "min_daily_spend": 1.0,  # минимальный расход в день ($)
                "volatility_threshold": 2.0,  # максимальный CV для волатильности (увеличено до 200%)
                "min_profitable_days": 2,  # минимум дней с прибылью для анализа
                "only_profitable_days": True  # учитывать только дни с revenue > 0 при расчете волатильности
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа кампаний",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "roi_threshold": {
                "label": "Минимальный ROI (%)",
                "description": "Минимальный средний ROI для включения в список",
                "type": "number",
                "min": 10,
                "max": 200,
                "default": 30
            },
            "max_daily_spend": {
                "label": "Максимальный расход в день ($)",
                "description": "Максимальный средний расход для поиска недооцененных кампаний",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 5.0
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
                "description": "Максимальный коэффициент вариации ROI (2.0 = 200%)",
                "type": "number",
                "min": 0.1,
                "max": 5.0,
                "default": 2.0
            },
            "min_profitable_days": {
                "label": "Минимум дней с прибылью",
                "description": "Минимальное количество дней с revenue > 0 для включения в анализ",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 2
            },
            "only_profitable_days": {
                "label": "Только прибыльные дни",
                "description": "Учитывать только дни с выручкой > 0 при расчете волатильности",
                "type": "boolean",
                "default": True
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ скрытых точек роста.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о скрытых жемчужинах
        """
        # Получение параметров
        days = config.params.get("days", 7)
        roi_threshold = config.params.get("roi_threshold", 30)
        max_daily_spend = config.params.get("max_daily_spend", 5.0)
        min_daily_spend = config.params.get("min_daily_spend", 1.0)
        volatility_threshold = config.params.get("volatility_threshold", 2.0)
        min_profitable_days = config.params.get("min_profitable_days", 2)
        only_profitable_days = config.params.get("only_profitable_days", True)

        # Период анализа
        date_from = datetime.now().date() - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
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
                "daily_stats": [],
                "days_with_data": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_revenue"] += revenue

                # Считаем дни с данными (расход > 0)
                if cost > 0:
                    campaigns_data[campaign_id]["days_with_data"] += 1

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue
                })

            # Обработка и поиск скрытых жемчужин
            hidden_gems = []
            total_campaigns_checked = 0
            high_potential_count = 0
            medium_potential_count = 0
            total_roi_sum = 0

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                # Расчет средних дневных метрик
                avg_daily_spend = data["total_cost"] / data["days_with_data"]

                # Фильтрация: расход в диапазоне
                if avg_daily_spend < min_daily_spend or avg_daily_spend > max_daily_spend:
                    continue

                # Фильтрация: должен быть хотя бы минимальный расход
                if data["total_cost"] < min_daily_spend:
                    continue

                total_campaigns_checked += 1

                # Расчет дневных ROI для анализа волатильности
                daily_roi_values = []
                profitable_days_count = 0

                for day_stat in data["daily_stats"]:
                    if day_stat["cost"] > 0:
                        roi = ((day_stat["revenue"] - day_stat["cost"]) / day_stat["cost"]) * 100

                        # Подсчет дней с выручкой
                        if day_stat["revenue"] > 0:
                            profitable_days_count += 1

                        # Если включен режим only_profitable_days, пропускаем дни без выручки
                        if only_profitable_days and day_stat["revenue"] == 0:
                            continue

                        daily_roi_values.append(roi)

                # Проверка минимального количества прибыльных дней
                if profitable_days_count < min_profitable_days:
                    continue

                # Нужно минимум 3 дня с данными для статистической значимости
                if len(daily_roi_values) < 3:
                    continue

                # Расчет статистики ROI
                avg_roi = statistics.mean(daily_roi_values)
                min_roi = min(daily_roi_values)
                max_roi = max(daily_roi_values)

                # Фильтрация: средний ROI должен быть >= roi_threshold
                if avg_roi < roi_threshold:
                    continue

                # Расчет волатильности (коэффициент вариации)
                # CV = std_dev / mean
                # CV корректен только для положительных средних значений
                if avg_roi > 0:
                    roi_volatility = statistics.stdev(daily_roi_values) / avg_roi
                else:
                    # Если средний ROI <= 0, пропускаем кампанию (не интересна для opportunities)
                    continue

                # Фильтрация: волатильность должна быть приемлемой
                if roi_volatility > volatility_threshold:
                    continue

                # Определение potential_rating
                # high: ROI > 50% AND volatility < 0.2
                # medium: остальные
                if avg_roi > 50 and roi_volatility < 0.2:
                    potential_rating = "high"
                    high_potential_count += 1
                else:
                    potential_rating = "medium"
                    medium_potential_count += 1

                total_roi_sum += avg_roi

                hidden_gems.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "avg_roi": round(avg_roi, 1),
                    "min_roi": round(min_roi, 1),
                    "max_roi": round(max_roi, 1),
                    "roi_volatility": round(roi_volatility, 2),
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "potential_rating": potential_rating
                })

            # Сортировка: сначала high potential, потом по avg_roi DESC
            hidden_gems.sort(key=lambda x: (
                0 if x["potential_rating"] == "high" else 1,
                -x["avg_roi"]
            ))

            return {
                "campaigns": hidden_gems,
                "summary": {
                    "total_gems": len(hidden_gems),
                    "high_potential": high_potential_count,
                    "medium_potential": medium_potential_count,
                    "total_checked": total_campaigns_checked,
                    "avg_roi": round(total_roi_sum / len(hidden_gems), 1) if hidden_gems else 0
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "roi_threshold": roi_threshold,
                    "max_daily_spend": max_daily_spend,
                    "min_daily_spend": min_daily_spend,
                    "volatility_threshold": volatility_threshold,
                    "min_profitable_days": min_profitable_days,
                    "only_profitable_days": only_profitable_days
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        hidden_gems = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})

        if not hidden_gems:
            return []

        charts = []

        # График распределения по потенциалу
        charts.append({
            "id": "gems_potential_chart",
            "type": "pie",
            "data": {
                "labels": ["Высокий потенциал", "Средний потенциал"],
                "datasets": [{
                    "data": [
                        summary.get("high_potential", 0),
                        summary.get("medium_potential", 0)
                    ],
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.8)",
                        "rgba(23, 162, 184, 0.8)"
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение по потенциалу"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График ROI для топ-10
        top_10 = hidden_gems[:10]
        charts.append({
            "id": "gems_roi_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Средний ROI (%)",
                    "data": [c["avg_roi"] for c in top_10],
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
                        "text": "Топ-10 по ROI"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        }
                    }
                }
            }
        })

        # График волатильности для топ-10
        charts.append({
            "id": "gems_volatility_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Волатильность (CV)",
                    "data": [c["roi_volatility"] for c in top_10],
                    "backgroundColor": "rgba(23, 162, 184, 0.6)",
                    "borderColor": "rgba(23, 162, 184, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по волатильности"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Коэффициент вариации"
                        }
                    }
                }
            }
        })

        # График среднего расхода для топ-10
        charts.append({
            "id": "gems_spend_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Средний расход в день ($)",
                    "data": [c["avg_daily_spend"] for c in top_10],
                    "backgroundColor": "rgba(255, 193, 7, 0.6)",
                    "borderColor": "rgba(255, 193, 7, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по расходу в день"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Расход ($)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для скрытых жемчужин.
        """
        hidden_gems = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not hidden_gems:
            return alerts

        # Общий алерт с краткой сводкой
        total_gems = summary.get("total_gems", 0)
        high_potential = summary.get("high_potential", 0)
        medium_potential = summary.get("medium_potential", 0)
        avg_roi = summary.get("avg_roi", 0)

        message = f"Найдено {total_gems} скрытых точек роста\n\n"
        message += f"Средний ROI: {avg_roi:.1f}%\n\n"

        # Высокий потенциал
        if high_potential > 0:
            high = [c for c in hidden_gems if c["potential_rating"] == "high"]
            message += f"Высокий потенциал ({high_potential} кампаний, ROI>50%, низкая волатильность):\n"
            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['avg_roi']:.1f}%, "
                message += f"${campaign['avg_daily_spend']:.2f}/день, "
                message += f"волатильность {campaign['roi_volatility']:.2f}\n"

        # Средний потенциал
        if medium_potential > 0:
            medium = [c for c in hidden_gems if c["potential_rating"] == "medium"]
            message += f"\nСредний потенциал ({medium_potential} кампаний, стабильный ROI>30%):\n"
            for i, campaign in enumerate(medium[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['avg_roi']:.1f}%, "
                message += f"${campaign['avg_daily_spend']:.2f}/день\n"

        severity = "medium"  # Это возможности, а не проблемы

        alerts.append({
            "type": "hidden_gems",
            "severity": severity,
            "message": message,
            "recommended_action": "Рассмотрите возможность масштабирования этих кампаний. Увеличьте бюджеты постепенно, отслеживая сохранение ROI",
            "total_gems": total_gems,
            "high_potential": high_potential,
            "medium_potential": medium_potential,
            "avg_roi": round(avg_roi, 1)
        })

        return alerts
