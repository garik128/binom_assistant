"""
Модуль обнаружения мертвых кампаний (зомби-кампаний)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
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


class ZombieCampaignDetector(BaseModule):
    """
    Детектор мертвых кампаний (зомби-кампаний).

    Находит кампании которые тратят деньги, генерируют клики, но не приносят лиды.
    Типичный признак проблем с лендингом или таргетингом.

    Критерии:
    - Расход > min_spend (по умолчанию $5/день)
    - Клики > min_clicks (по умолчанию 20/день)
    - Лиды = 0 ИЛИ CR < min_cr (по умолчанию 0.1%)
    - Продолжается > min_days (по умолчанию 2 дней)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="zombie_campaign_detector",
            name="Мертвые кампании",
            category="problem_detection",
            description="Находит кампании с тратами но без лидов",
            detailed_description="Модуль находит зомби-кампании которые тратят деньги, генерируют клики, но не приносят лиды. Помогает выявить проблемы с лендингом или таргетингом.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["zombie", "waste", "clicks", "leads"]
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
                "min_spend": 5.0,  # минимальный расход в день ($)
                "min_clicks": 20,  # минимум кликов в день
                "min_cr": 0.1,  # минимальный CR для алерта (%)
                "min_days": 2,  # минимум дней с проблемой
                "severity_critical_leads": 0,  # количество лидов для critical severity
                "severity_high_cr": 0.1  # CR для high severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа зомби-кампаний",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_spend": {
                "label": "Минимальный расход в день ($)",
                "description": "Минимальный средний расход для включения в анализ",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 5.0
            },
            "min_clicks": {
                "label": "Минимум кликов в день",
                "description": "Минимальное среднее количество кликов в день",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 20
            },
            "min_cr": {
                "label": "Минимальный CR (%)",
                "description": "Минимальный CR для определения зомби (если CR ниже - проблема)",
                "type": "number",
                "min": 0.01,
                "max": 5.0,
                "default": 0.1
            },
            "min_days": {
                "label": "Минимум дней с проблемой",
                "description": "Минимальное количество дней продолжения проблемы",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 2
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "leads_and_cr",
            "metric_label": "Лиды и CR",
            "metric_unit": "",
            "description": "Пороги критичности на основе количества лидов и CR",
            "thresholds": {
                "severity_critical_leads": {
                    "label": "Критичное количество лидов",
                    "description": "Количество лидов для критичного уровня (0 = нет лидов)",
                    "type": "number",
                    "min": 0,
                    "max": 5,
                    "step": 1,
                    "default": 0
                },
                "severity_high_cr": {
                    "label": "Высокий CR (%)",
                    "description": "CR ниже этого значения считается высокой важности",
                    "type": "number",
                    "min": 0.01,
                    "max": 1.0,
                    "step": 0.1,
                    "default": 0.1
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично (0 лидов)", "color": "#ef4444", "condition": "leads == 0"},
                {"value": "high", "label": "Высокий (низкий CR)", "color": "#f59e0b", "condition": "CR < min_cr"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ зомби-кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о зомби-кампаниях
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_spend = config.params.get("min_spend", 5.0)
        min_clicks = config.params.get("min_clicks", 20)
        min_cr = config.params.get("min_cr", 0.1)
        min_days = config.params.get("min_days", 2)

        # Получение настраиваемых порогов severity
        severity_critical_leads = config.params.get("severity_critical_leads", 0)
        severity_high_cr = config.params.get("severity_high_cr", 0.1)

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
                "total_cost": 0,
                "total_clicks": 0,
                "total_leads": 0,
                "daily_stats": [],
                "days_with_data": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                cost = float(row.cost) if row.cost else 0
                clicks = row.clicks or 0
                leads = row.leads or 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_clicks"] += clicks
                campaigns_data[campaign_id]["total_leads"] += leads

                # Считаем дни с данными (расход > 0 или клики > 0)
                if cost > 0 or clicks > 0:
                    campaigns_data[campaign_id]["days_with_data"] += 1

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "clicks": clicks,
                    "leads": leads
                })

            # Обработка и поиск зомби-кампаний
            problem_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0
            total_wasted = 0

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                # Расчет средних дневных метрик
                avg_daily_cost = data["total_cost"] / data["days_with_data"]
                avg_daily_clicks = data["total_clicks"] / data["days_with_data"]

                # Фильтрация: минимальный расход и клики
                if avg_daily_cost < min_spend:
                    continue
                if avg_daily_clicks < min_clicks:
                    continue

                total_campaigns_checked += 1

                # Расчет CR
                conversion_rate = (data["total_leads"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0

                # Проверка критериев зомби на основе настраиваемых порогов
                # Severity: critical если leads <= severity_critical_leads, high если CR < severity_high_cr
                is_zombie = False
                severity = None
                severity_label = None

                if data["total_leads"] <= severity_critical_leads:
                    # Критично: совсем нет лидов
                    is_zombie = True
                    severity = "critical"
                    severity_label = "Критично (0 лидов)"
                    critical_count += 1
                elif conversion_rate < severity_high_cr:
                    # Высокий: очень низкий CR
                    is_zombie = True
                    severity = "high"
                    severity_label = f"Высокий (CR < {severity_high_cr}%)"
                    high_count += 1

                if not is_zombie:
                    continue

                # Проверка минимальной продолжительности проблемы
                # Считаем количество дней с проблемой (есть клики/расход, но нет лидов или низкий CR)
                days_with_problem = 0
                for day_stat in data["daily_stats"]:
                    if day_stat["cost"] > 0 or day_stat["clicks"] > 0:
                        # Есть активность
                        day_cr = (day_stat["leads"] / day_stat["clicks"] * 100) if day_stat["clicks"] > 0 else 0
                        if day_stat["leads"] == 0 or day_cr < min_cr:
                            # Проблема присутствует в этот день
                            days_with_problem += 1

                # Фильтр: проблема должна быть минимум min_days дней
                if days_with_problem < min_days:
                    continue

                # Весь расход считается потраченным впустую
                wasted_budget = data["total_cost"]
                total_wasted += wasted_budget

                problem_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_cost": round(data["total_cost"], 2),
                    "avg_daily_cost": round(avg_daily_cost, 2),
                    "total_clicks": data["total_clicks"],
                    "avg_daily_clicks": round(avg_daily_clicks, 1),
                    "total_leads": data["total_leads"],
                    "conversion_rate": round(conversion_rate, 2),
                    "days_with_problem": days_with_problem,
                    "wasted_budget": round(wasted_budget, 2),
                    "severity": severity,
                    "severity_label": severity_label
                })

            # Сортировка: сначала с наибольшим потраченным впустую бюджетом
            problem_campaigns.sort(key=lambda x: x["wasted_budget"], reverse=True)

            return {
                "campaigns": problem_campaigns,
                "summary": {
                    "total_problems": len(problem_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "total_checked": total_campaigns_checked,
                    "total_wasted": round(total_wasted, 2)
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_spend": min_spend,
                    "min_clicks": min_clicks,
                    "min_cr": min_cr,
                    "min_days": min_days
                },
                "thresholds": {
                    "severity_critical_leads": severity_critical_leads,
                    "severity_high_cr": severity_high_cr
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        problem_campaigns = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})

        if not problem_campaigns:
            return []

        charts = []

        # График распределения по критичности
        charts.append({
            "id": "zombie_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично (0 лидов)", "Высокий (низкий CR)"],
                "datasets": [{
                    "data": [
                        summary.get("critical_count", 0),
                        summary.get("high_count", 0)
                    ],
                    "backgroundColor": [
                        "rgba(220, 53, 69, 0.8)",
                        "rgba(255, 159, 64, 0.8)"
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение по критичности"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График потраченного впустую бюджета для топ-10
        top_10 = problem_campaigns[:10]
        charts.append({
            "id": "zombie_wasted_budget_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Потрачено впустую ($)",
                    "data": [c["wasted_budget"] for c in top_10],
                    "backgroundColor": "rgba(220, 53, 69, 0.6)",
                    "borderColor": "rgba(220, 53, 69, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по потраченному впустую бюджету"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Потрачено впустую ($)"
                        }
                    }
                }
            }
        })

        # График среднедневного расхода для топ-10
        charts.append({
            "id": "zombie_daily_cost_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Средний расход в день ($)",
                    "data": [c["avg_daily_cost"] for c in top_10],
                    "backgroundColor": "rgba(255, 159, 64, 0.6)",
                    "borderColor": "rgba(255, 159, 64, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по среднедневному расходу"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Расход в день ($)"
                        }
                    }
                }
            }
        })

        # График среднедневных кликов для топ-10
        charts.append({
            "id": "zombie_daily_clicks_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Средние клики в день",
                    "data": [c["avg_daily_clicks"] for c in top_10],
                    "backgroundColor": "rgba(54, 162, 235, 0.6)",
                    "borderColor": "rgba(54, 162, 235, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по среднедневным кликам"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Клики в день"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для зомби-кампаний.
        """
        problem_campaigns = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not problem_campaigns:
            return alerts

        # Общий алерт с краткой сводкой
        total_wasted = summary.get("total_wasted", 0)
        critical_count = summary.get("critical_count", 0)
        high_count = summary.get("high_count", 0)

        message = f"Обнаружено {len(problem_campaigns)} зомби-кампаний (траты без лидов)\n\n"
        message += f"Всего потрачено впустую: ${total_wasted:.2f}\n\n"

        # Критичные (0 лидов)
        if critical_count > 0:
            critical = [c for c in problem_campaigns if c["severity"] == "critical"]
            message += f"Критичные ({critical_count} кампаний, 0 лидов):\n"
            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"${campaign['avg_daily_cost']:.2f}/день, "
                message += f"{campaign['avg_daily_clicks']:.0f} кликов/день, "
                message += f"потрачено ${campaign['wasted_budget']:.2f}\n"

        # Высокий уровень (низкий CR)
        if high_count > 0:
            high = [c for c in problem_campaigns if c["severity"] == "high"]
            message += f"\nВысокий уровень ({high_count} кампаний, очень низкий CR):\n"
            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CR {campaign['conversion_rate']:.2f}%, "
                message += f"${campaign['avg_daily_cost']:.2f}/день, "
                message += f"потрачено ${campaign['wasted_budget']:.2f}\n"

        severity = "critical" if critical_count > 0 else "high"

        alerts.append({
            "type": "zombie_campaign",
            "severity": severity,
            "message": message,
            "recommended_action": "Срочно проверьте лендинги, таргетинг и качество источников. Остановите кампании или пересмотрите настройки",
            "campaigns_count": len(problem_campaigns),
            "total_wasted": round(total_wasted, 2),
            "critical_count": critical_count,
            "high_count": high_count
        })

        return alerts
