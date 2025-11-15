"""
Модуль обнаружения падения конверсии
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


class ConversionDropAlert(BaseModule):
    """
    Детектор падения конверсии кампаний.

    Находит кампании с резким падением CR (conversion rate).

    Критерии:
    - Сравнивает CR текущих N дней с предыдущими N днями
    - CR = (leads / clicks) * 100
    - Находит кампании где CR упал более чем на drop_threshold%
    - Фильтрация: минимум min_clicks кликов за текущий период
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="conversion_drop_alert",
            name="Падение конверсии",
            category="problem_detection",
            description="Обнаруживает падение CR кампаний",
            detailed_description="Модуль находит кампании с резким падением конверсии лидов. Сравнивает CR текущих дней с предыдущим периодом.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["conversion", "cr", "monitoring", "problems"]
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
                "drop_threshold": 30,  # порог падения CR (%)
                "min_clicks": 100,  # минимум кликов за текущий период
                "severity_critical_drop": 50,  # падение CR для critical severity (%)
                "severity_high_drop": 30  # падение CR для high severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для текущего и предыдущего периода",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "drop_threshold": {
                "label": "Порог падения CR (%)",
                "description": "Минимальное падение CR для определения проблемы",
                "type": "number",
                "min": 10,
                "max": 90,
                "default": 30
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов за текущий период",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 100
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "cr_drop",
            "metric_label": "Падение CR",
            "metric_unit": "%",
            "description": "Пороги критичности на основе падения конверсии",
            "thresholds": {
                "severity_critical_drop": {
                    "label": "Критичное падение CR (%)",
                    "description": "Падение CR выше этого значения считается критичным",
                    "type": "number",
                    "min": 30,
                    "max": 90,
                    "step": 5,
                    "default": 50
                },
                "severity_high_drop": {
                    "label": "Высокое падение CR (%)",
                    "description": "Падение CR выше этого значения (но ниже критичного) считается высокой важности",
                    "type": "number",
                    "min": 10,
                    "max": 60,
                    "step": 5,
                    "default": 30
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "drop >= 50%"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "drop >= 30%"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ падения конверсии кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с падением CR
        """
        # Получение параметров
        days = config.params.get("days", 7)
        drop_threshold = config.params.get("drop_threshold", 30)
        min_clicks = config.params.get("min_clicks", 100)

        # Получение настраиваемых порогов severity
        severity_critical_drop = config.params.get("severity_critical_drop", 50)
        severity_high_drop = config.params.get("severity_high_drop", 30)

        # Период анализа: последние 2*days дней
        # ИСКЛЮЧАЕМ сегодняшний день (неполные данные могут давать ложные алерты)
        yesterday = datetime.now().date() - timedelta(days=1)
        total_days = days * 2
        date_from = yesterday - timedelta(days=total_days - 1)
        split_date = yesterday - timedelta(days=days - 1)

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
                CampaignStatsDaily.leads
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.date <= yesterday  # Исключаем сегодняшний день
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
                "current_period": {
                    "clicks": 0,
                    "leads": 0
                },
                "previous_period": {
                    "clicks": 0,
                    "leads": 0
                },
                "daily_stats": []
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                clicks = row.clicks or 0
                leads = row.leads or 0

                # Разделяем на current и previous периоды
                if row.date >= split_date:
                    # Current период (последние days дней)
                    campaigns_data[campaign_id]["current_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["current_period"]["leads"] += leads
                else:
                    # Previous период (предыдущие days дней)
                    campaigns_data[campaign_id]["previous_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["previous_period"]["leads"] += leads

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "clicks": clicks,
                    "leads": leads
                })

            # Обработка и поиск кампаний с падением CR
            problem_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0

            for campaign_id, data in campaigns_data.items():
                current = data["current_period"]
                previous = data["previous_period"]

                # Фильтрация: минимум кликов за текущий период
                if current["clicks"] < min_clicks:
                    continue

                # Фильтрация: должны быть клики в предыдущем периоде
                if previous["clicks"] < min_clicks:
                    continue

                total_campaigns_checked += 1

                # Расчет CR для текущего периода
                current_cr = (current["leads"] / current["clicks"] * 100) if current["clicks"] > 0 else 0

                # Расчет CR для предыдущего периода
                previous_cr = (previous["leads"] / previous["clicks"] * 100) if previous["clicks"] > 0 else 0

                # Расчет падения CR
                if previous_cr > 0:
                    cr_drop_percent = ((previous_cr - current_cr) / previous_cr) * 100
                else:
                    # Если предыдущий CR был 0, то падение не имеет смысла
                    continue

                # Проверка критерия падения
                if cr_drop_percent < drop_threshold:
                    continue

                # Определение критичности на основе настраиваемых порогов
                if cr_drop_percent >= severity_critical_drop:
                    severity = "critical"
                    severity_label = f"Критично (>{severity_critical_drop}%)"
                    critical_count += 1
                else:
                    severity = "high"
                    severity_label = f"Высокий (>{severity_high_drop}%)"
                    high_count += 1

                problem_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "current_cr": round(current_cr, 2),
                    "previous_cr": round(previous_cr, 2),
                    "cr_drop_percent": round(cr_drop_percent, 1),
                    "current_clicks": current["clicks"],
                    "current_leads": current["leads"],
                    "previous_clicks": previous["clicks"],
                    "previous_leads": previous["leads"],
                    "severity": severity,
                    "severity_label": severity_label
                })

            # Сортировка: сначала с наибольшим падением CR
            problem_campaigns.sort(key=lambda x: x["cr_drop_percent"], reverse=True)

            return {
                "campaigns": problem_campaigns,
                "summary": {
                    "total_problems": len(problem_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "split_date": split_date.isoformat(),
                    "date_to": yesterday.isoformat()  # Исключаем сегодняшний день
                },
                "params": {
                    "drop_threshold": drop_threshold,
                    "min_clicks": min_clicks
                },
                "thresholds": {
                    "severity_critical_drop": severity_critical_drop,
                    "severity_high_drop": severity_high_drop
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
            "id": "conversion_drop_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично (>50%)", "Высокий (>30%)"],
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

        # График падения CR для топ-10
        top_10 = problem_campaigns[:10]
        charts.append({
            "id": "conversion_drop_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "Предыдущий CR (%)",
                        "data": [c["previous_cr"] for c in top_10],
                        "backgroundColor": "rgba(75, 192, 192, 0.6)",
                        "borderColor": "rgba(75, 192, 192, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "Текущий CR (%)",
                        "data": [c["current_cr"] for c in top_10],
                        "backgroundColor": "rgba(220, 53, 69, 0.6)",
                        "borderColor": "rgba(220, 53, 69, 1)",
                        "borderWidth": 1
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по падению CR"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "CR (%)"
                        }
                    }
                }
            }
        })

        # График процента падения для топ-10
        charts.append({
            "id": "conversion_drop_percent_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Падение CR (%)",
                    "data": [c["cr_drop_percent"] for c in top_10],
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
                        "text": "Топ-10 по проценту падения CR"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Падение (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с падением CR.
        """
        problem_campaigns = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        # Критичные (падение > 50%)
        critical = [c for c in problem_campaigns if c["severity"] == "critical"]
        if critical:
            message = f"Обнаружено {len(critical)} кампаний с критическим падением CR (>50%)\n\n"
            message += "Топ-3 по падению:\n"

            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CR {campaign['previous_cr']:.2f}% -> {campaign['current_cr']:.2f}% "
                message += f"(падение {campaign['cr_drop_percent']:.1f}%)\n"

            alerts.append({
                "type": "conversion_drop_critical",
                "severity": "critical",
                "message": message,
                "recommended_action": "Срочно проверьте качество трафика, лендинги и оффер",
                "campaigns_count": len(critical),
                "avg_drop": round(sum(c["cr_drop_percent"] for c in critical) / len(critical), 1)
            })

        # Высокий уровень (падение > 30%)
        high = [c for c in problem_campaigns if c["severity"] == "high"]
        if high:
            message = f"Обнаружено {len(high)} кампаний с падением CR (>30%)\n\n"
            message += "Требуют внимания:\n"

            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CR {campaign['previous_cr']:.2f}% -> {campaign['current_cr']:.2f}% "
                message += f"(падение {campaign['cr_drop_percent']:.1f}%)\n"

            alerts.append({
                "type": "conversion_drop_high",
                "severity": "high",
                "message": message,
                "recommended_action": "Проверьте настройки таргетинга и качество источников",
                "campaigns_count": len(high),
                "avg_drop": round(sum(c["cr_drop_percent"] for c in high) / len(high), 1)
            })

        return alerts
