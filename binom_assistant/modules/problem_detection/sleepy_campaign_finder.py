"""
Модуль поиска заснувших кампаний
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


class SleepyCampaignFinder(BaseModule):
    """
    Детектор заснувших кампаний.

    Находит кампании, которые были активны, но перестали получать трафик.

    Критерии:
    - Были клики/расход в предыдущие 7 дней (history)
    - НЕТ или резкое падение кликов/расхода последние 3 дня (recent)
    - Падение >= 90% трафика (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="sleepy_campaign_finder",
            name="Заснувшие кампании",
            category="problem_detection",
            description="Находит остановившиеся кампании",
            detailed_description="Модуль находит кампании, которые были активны, но перестали получать трафик. Сравнивает последние 3 дня с предыдущими 7 днями.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["traffic", "monitoring", "problems", "campaigns"]
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
                "recent_days": 3,  # дней "тишины"
                "history_days": 7,  # дней истории для сравнения
                "min_clicks_before": 50,  # минимум кликов "до"
                "drop_threshold": 90,  # порог падения (%)
                "severity_critical_clicks": 0,  # клики для critical severity
                "severity_high_drop": 95  # падение для high severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "recent_days": {
                "label": "Дней тишины",
                "description": "Количество последних дней без активности",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 3
            },
            "history_days": {
                "label": "Дней истории",
                "description": "Количество дней истории для сравнения",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "min_clicks_before": {
                "label": "Минимум кликов до",
                "description": "Минимальное количество кликов в период истории",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 50
            },
            "drop_threshold": {
                "label": "Порог падения (%)",
                "description": "Процент падения трафика для определения 'заснувшей' кампании",
                "type": "number",
                "min": 50,
                "max": 100,
                "default": 90
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "clicks_and_drop",
            "metric_label": "Клики и падение",
            "metric_unit": "",
            "description": "Пороги критичности на основе кликов и процента падения",
            "thresholds": {
                "severity_critical_clicks": {
                    "label": "Критичные клики",
                    "description": "Количество кликов для критичного уровня (0 = полная остановка)",
                    "type": "number",
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "default": 0
                },
                "severity_high_drop": {
                    "label": "Высокое падение (%)",
                    "description": "Процент падения для высокого уровня важности",
                    "type": "number",
                    "min": 80,
                    "max": 100,
                    "step": 5,
                    "default": 95
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "clicks_recent == 0"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "drop >= 95%"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "drop >= threshold"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Поиск заснувших кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о заснувших кампаниях
        """
        # Получение параметров
        recent_days = config.params.get("recent_days", 3)
        history_days = config.params.get("history_days", 7)
        min_clicks_before = config.params.get("min_clicks_before", 50)
        drop_threshold = config.params.get("drop_threshold", 90)

        # Получение настраиваемых порогов severity
        severity_critical_clicks = config.params.get("severity_critical_clicks", 0)
        severity_high_drop = config.params.get("severity_high_drop", 95)

        # ИСКЛЮЧАЕМ сегодняшний день (неполные данные могут давать ложные алерты)
        yesterday = datetime.now().date() - timedelta(days=1)
        total_days = recent_days + history_days
        date_from = yesterday - timedelta(days=total_days - 1)
        split_date = yesterday - timedelta(days=recent_days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с кликами за весь период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.cost
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
                "history_clicks": 0,
                "recent_clicks": 0,
                "history_cost": 0,
                "recent_cost": 0,
                "daily_stats": []
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                clicks = row.clicks or 0
                cost = float(row.cost) if row.cost else 0

                # Разделяем на history и recent периоды
                if row.date <= split_date:
                    # History период (более старые данные)
                    campaigns_data[campaign_id]["history_clicks"] += clicks
                    campaigns_data[campaign_id]["history_cost"] += cost
                else:
                    # Recent период (последние recent_days дней)
                    campaigns_data[campaign_id]["recent_clicks"] += clicks
                    campaigns_data[campaign_id]["recent_cost"] += cost

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "clicks": clicks,
                    "cost": cost
                })

            # Обработка и поиск заснувших кампаний
            sleepy_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0
            medium_count = 0

            for campaign_id, data in campaigns_data.items():
                clicks_before = data["history_clicks"]
                clicks_recent = data["recent_clicks"]

                # Фильтрация: минимум кликов "до"
                if clicks_before < min_clicks_before:
                    continue

                total_campaigns_checked += 1

                # Расчет падения на основе средних значений в день
                # Правильное сравнение: avg_before vs avg_recent
                avg_clicks_before = clicks_before / history_days if history_days > 0 else 0
                avg_clicks_recent = clicks_recent / recent_days if recent_days > 0 else 0

                if avg_clicks_before > 0:
                    drop_percent = ((avg_clicks_before - avg_clicks_recent) / avg_clicks_before) * 100
                else:
                    drop_percent = 0

                # Проверка критерия "заснувшей"
                if clicks_recent == 0 or drop_percent >= drop_threshold:
                    # Находим последнюю активность (последний день с кликами > 0)
                    last_activity_date = None
                    for stat in reversed(data["daily_stats"]):
                        if stat["clicks"] > 0:
                            last_activity_date = stat["date"]
                            break

                    # Рассчитываем дни молчания (от последней активности до вчера)
                    if last_activity_date:
                        days_silent = (yesterday - last_activity_date).days
                    else:
                        days_silent = total_days

                    # Определение критичности на основе настраиваемых порогов
                    if clicks_recent <= severity_critical_clicks:
                        severity = "critical"
                        severity_label = "Критично"
                        critical_count += 1
                    elif drop_percent >= severity_high_drop:
                        severity = "high"
                        severity_label = "Высокий"
                        high_count += 1
                    else:
                        severity = "medium"
                        severity_label = "Средний"
                        medium_count += 1

                    sleepy_campaigns.append({
                        "campaign_id": campaign_id,
                        "binom_id": data["binom_id"],
                        "name": data["name"],
                        "group": data["group"],
                        "clicks_before": clicks_before,
                        "clicks_recent": clicks_recent,
                        "avg_clicks_before": round(avg_clicks_before, 1),
                        "avg_clicks_recent": round(avg_clicks_recent, 1),
                        "drop_percent": round(drop_percent, 1),
                        "cost_before": round(data["history_cost"], 2),
                        "cost_recent": round(data["recent_cost"], 2),
                        "last_activity_date": last_activity_date.isoformat() if last_activity_date else None,
                        "days_silent": days_silent,
                        "severity": severity,
                        "severity_label": severity_label
                    })

            # Сортировка: сначала по clicks_before DESC (самые активные были)
            sleepy_campaigns.sort(key=lambda x: x["clicks_before"], reverse=True)

            return {
                "sleepy_campaigns": sleepy_campaigns,
                "summary": {
                    "total_sleepy": len(sleepy_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "medium_count": medium_count,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "recent_days": recent_days,
                    "history_days": history_days,
                    "date_from": date_from.isoformat(),
                    "split_date": split_date.isoformat(),
                    "date_to": yesterday.isoformat()  # Исключаем сегодняшний день
                },
                "params": {
                    "min_clicks_before": min_clicks_before,
                    "drop_threshold": drop_threshold
                },
                "thresholds": {
                    "severity_critical_clicks": severity_critical_clicks,
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
        sleepy_campaigns = raw_data.get("sleepy_campaigns", [])
        summary = raw_data.get("summary", {})

        if not sleepy_campaigns:
            return []

        charts = []

        # График распределения по критичности
        charts.append({
            "id": "sleepy_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично", "Высокий", "Средний"],
                "datasets": [{
                    "data": [
                        summary.get("critical_count", 0),
                        summary.get("high_count", 0),
                        summary.get("medium_count", 0)
                    ],
                    "backgroundColor": [
                        "rgba(220, 53, 69, 0.8)",
                        "rgba(255, 159, 64, 0.8)",
                        "rgba(255, 205, 86, 0.8)"
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

        # График падения трафика для топ-10
        top_10 = sleepy_campaigns[:10]
        charts.append({
            "id": "sleepy_drop_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Падение трафика (%)",
                    "data": [c["drop_percent"] for c in top_10],
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
                        "text": "Топ-10 по падению трафика"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 100,
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
        Генерация алертов для заснувших кампаний.
        """
        sleepy_campaigns = raw_data.get("sleepy_campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        # Критичные (полная остановка)
        critical = [c for c in sleepy_campaigns if c["severity"] == "critical"]
        if critical:
            message = f"Обнаружено {len(critical)} кампаний с полной остановкой трафика\n\n"
            message += "Топ-3 по предыдущей активности:\n"

            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"было {campaign['clicks_before']} кликов, "
                message += f"молчит {campaign['days_silent']} дней\n"

            alerts.append({
                "type": "sleepy_campaigns_critical",
                "severity": "critical",
                "message": message,
                "recommended_action": "Срочно проверьте источники трафика и настройки кампаний",
                "campaigns_count": len(critical),
                "avg_days_silent": round(sum(c["days_silent"] for c in critical) / len(critical), 1)
            })

        # Высокий уровень (падение >= 95%)
        high = [c for c in sleepy_campaigns if c["severity"] == "high"]
        if high:
            message = f"Обнаружено {len(high)} кампаний с критическим падением трафика (>95%)\n\n"
            message += "Требуют внимания:\n"

            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"падение {campaign['drop_percent']:.1f}% "
                message += f"({campaign['clicks_before']} → {campaign['clicks_recent']} кликов)\n"

            alerts.append({
                "type": "sleepy_campaigns_high",
                "severity": "high",
                "message": message,
                "recommended_action": "Проверьте качество источников и настройки таргетинга",
                "campaigns_count": len(high),
                "avg_drop": round(sum(c["drop_percent"] for c in high) / len(high), 1)
            })

        return alerts
