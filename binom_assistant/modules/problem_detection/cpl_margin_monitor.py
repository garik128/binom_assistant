"""
Модуль мониторинга маржи в CPL кампаниях
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


class CPLMarginMonitor(BaseModule):
    """
    Мониторинг маржи в CPL кампаниях.

    CPL кампания - это кампания где оплата происходит сразу за лид (без апрувов).
    Признак: a_leads == 0, но revenue > 0

    Критерии:
    - Только CPL кампании (a_leads == 0 AND revenue > 0)
    - Рассчитывает margin = revenue - cost
    - Рассчитывает margin_percent = (margin / revenue) * 100
    - Находит кампании где margin < порога или margin_percent < порога
    - Сравнивает margin за последние N дней с предыдущими N днями
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="cpl_margin_monitor",
            name="Маржа CPL",
            category="problem_detection",
            description="Следит за margin в CPL кампаниях",
            detailed_description="Модуль отслеживает маржу (прибыль) в CPL кампаниях, где оплата происходит сразу за лид. Находит кампании с низкой маржой и отслеживает её динамику. Анализирует только полные дни, исключая сегодняшний (данные могут быть неполными).",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["cpl", "margin", "profit", "monitoring"]
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
                "days": 7,  # период анализа
                "min_revenue": 10,  # минимум revenue для анализа
                "margin_threshold": 5,  # минимум margin ($)
                "margin_percent_threshold": 20,  # минимум margin (%)
                "severity_critical_margin": 0,  # margin для critical severity ($)
                "severity_high_percent": 10  # margin_percent для high severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для текущего периода",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_revenue": {
                "label": "Минимум revenue",
                "description": "Минимальный revenue для включения в анализ ($)",
                "type": "number",
                "min": 1,
                "max": 100,
                "default": 10
            },
            "margin_threshold": {
                "label": "Минимум margin ($)",
                "description": "Порог минимальной маржи в долларах",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 5
            },
            "margin_percent_threshold": {
                "label": "Минимум margin (%)",
                "description": "Порог минимальной маржи в процентах",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 20
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "margin",
            "metric_label": "Маржа",
            "metric_unit": "$ / %",
            "description": "Пороги критичности на основе маржи в CPL кампаниях",
            "thresholds": {
                "severity_critical_margin": {
                    "label": "Критичная маржа ($)",
                    "description": "Маржа ниже этого значения считается критичной (0 = убыток)",
                    "type": "number",
                    "min": -50,
                    "max": 10,
                    "step": 1,
                    "default": 0
                },
                "severity_high_percent": {
                    "label": "Высокая маржа (%)",
                    "description": "Процент маржи ниже этого значения (но выше критичной) считается высокой важности",
                    "type": "number",
                    "min": 5,
                    "max": 30,
                    "step": 5,
                    "default": 10
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично (убыток)", "color": "#ef4444", "condition": "margin < 0"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "margin_percent < 10%"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "margin_percent < 20%"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ маржи в CPL кампаниях.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с проблемной маржой
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_revenue = config.params.get("min_revenue", 10)
        margin_threshold = config.params.get("margin_threshold", 5)
        margin_percent_threshold = config.params.get("margin_percent_threshold", 20)

        # Получение настраиваемых порогов severity
        severity_critical_margin = config.params.get("severity_critical_margin", 0)
        severity_high_percent = config.params.get("severity_high_percent", 10)

        # Период анализа: последние 14 дней (2 периода по days дней)
        # Исключаем сегодняшний день (данные могут быть неполными)
        total_days = days * 2
        date_from = datetime.now().date() - timedelta(days=total_days)
        split_date = datetime.now().date() - timedelta(days=days)

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
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.a_leads,
                CampaignStatsDaily.r_leads  # Для определения CPA кампаний
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
                "current_period": {
                    "revenue": 0,
                    "cost": 0,
                    "a_leads": 0
                },
                "previous_period": {
                    "revenue": 0,
                    "cost": 0,
                    "a_leads": 0
                },
                "total_a_leads_ever": 0,  # Всего апрувов за ВСЕ время
                "total_r_leads_ever": 0,  # Всего отказов за ВСЕ время
                "daily_stats": []
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                revenue = float(row.revenue) if row.revenue else 0
                cost = float(row.cost) if row.cost else 0
                a_leads = row.a_leads or 0
                r_leads = row.r_leads or 0

                # Считаем общее количество апрувов и отказов за ВСЕ время
                campaigns_data[campaign_id]["total_a_leads_ever"] += a_leads
                campaigns_data[campaign_id]["total_r_leads_ever"] += r_leads

                # Разделяем на current и previous периоды
                if row.date >= split_date:
                    # Current период (последние days дней)
                    campaigns_data[campaign_id]["current_period"]["revenue"] += revenue
                    campaigns_data[campaign_id]["current_period"]["cost"] += cost
                    campaigns_data[campaign_id]["current_period"]["a_leads"] += a_leads
                else:
                    # Previous период (предыдущие days дней)
                    campaigns_data[campaign_id]["previous_period"]["revenue"] += revenue
                    campaigns_data[campaign_id]["previous_period"]["cost"] += cost
                    campaigns_data[campaign_id]["previous_period"]["a_leads"] += a_leads

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "revenue": revenue,
                    "cost": cost,
                    "a_leads": a_leads
                })

            # Обработка и поиск проблемных кампаний
            problem_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0
            medium_count = 0

            for campaign_id, data in campaigns_data.items():
                current = data["current_period"]
                previous = data["previous_period"]

                # КРИТИЧНО: Фильтр CPL кампаний
                # CPL кампания: НИКОГДА не было апрувов/отказов (a_leads=0, r_leads=0) И есть revenue
                # Проверяем за ВСЕ время, а не только текущий период
                # Это защищает от ложного определения молодых CPA кампаний как CPL

                if data["total_a_leads_ever"] > 0 or data["total_r_leads_ever"] > 0:
                    # Это CPA кампания (были апрувы или отказы)
                    continue

                if current["revenue"] <= 0:
                    # Нет revenue - не CPL
                    continue

                # Фильтрация: минимум revenue
                if current["revenue"] < min_revenue:
                    continue

                total_campaigns_checked += 1

                # Расчет margin для текущего периода
                margin_current = current["revenue"] - current["cost"]
                margin_percent_current = (margin_current / current["revenue"] * 100) if current["revenue"] > 0 else 0

                # Расчет margin для предыдущего периода
                margin_previous = previous["revenue"] - previous["cost"]

                # Расчет тренда margin
                margin_trend = margin_current - margin_previous

                # Проверка критериев проблемной маржи
                is_problem = (
                    margin_current < margin_threshold or
                    margin_percent_current < margin_percent_threshold
                )

                if not is_problem:
                    continue

                # Определение критичности на основе настраиваемых порогов
                if margin_current < severity_critical_margin:
                    # Убыток
                    severity = "critical"
                    severity_label = "Критично (убыток)"
                    critical_count += 1
                elif margin_percent_current < severity_high_percent:
                    severity = "high"
                    severity_label = f"Высокий (<{severity_high_percent}%)"
                    high_count += 1
                else:
                    severity = "medium"
                    severity_label = f"Средний (<{margin_percent_threshold}%)"
                    medium_count += 1

                problem_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "revenue": round(current["revenue"], 2),
                    "cost": round(current["cost"], 2),
                    "margin": round(margin_current, 2),
                    "margin_percent": round(margin_percent_current, 1),
                    "previous_margin": round(margin_previous, 2),
                    "margin_trend": round(margin_trend, 2),
                    "severity": severity,
                    "severity_label": severity_label
                })

            # Сортировка: сначала с самой низкой маржой (margin ASC)
            problem_campaigns.sort(key=lambda x: x["margin"])

            return {
                "problem_campaigns": problem_campaigns,
                "summary": {
                    "total_problems": len(problem_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "medium_count": medium_count,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "split_date": split_date.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_revenue": min_revenue,
                    "margin_threshold": margin_threshold,
                    "margin_percent_threshold": margin_percent_threshold
                },
                "thresholds": {
                    "severity_critical_margin": severity_critical_margin,
                    "severity_high_percent": severity_high_percent
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        problem_campaigns = raw_data.get("problem_campaigns", [])
        summary = raw_data.get("summary", {})

        if not problem_campaigns:
            return []

        charts = []

        # График распределения по критичности
        charts.append({
            "id": "cpl_margin_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично (убыток)", "Высокий (<10%)", "Средний (<20%)"],
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

        # График маржи для топ-10
        top_10 = problem_campaigns[:10]
        charts.append({
            "id": "cpl_margin_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Margin (%)",
                    "data": [c["margin_percent"] for c in top_10],
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
                        "text": "Топ-10 кампаний с низкой маржой"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Margin (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с проблемной маржой.
        """
        problem_campaigns = raw_data.get("problem_campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        # Критичные (убыток)
        critical = [c for c in problem_campaigns if c["severity"] == "critical"]
        if critical:
            message = f"Обнаружено {len(critical)} CPL кампаний с убытком\n\n"
            message += "Топ-3 с наибольшим убытком:\n"

            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"margin {campaign['margin']:.2f}$ "
                message += f"({campaign['margin_percent']:.1f}%)\n"

            alerts.append({
                "type": "cpl_margin_critical",
                "severity": "critical",
                "message": message,
                "recommended_action": "Срочно проверьте цены оффера и стоимость трафика",
                "campaigns_count": len(critical),
                "avg_margin": round(sum(c["margin"] for c in critical) / len(critical), 2)
            })

        # Высокий уровень (margin < 10%)
        high = [c for c in problem_campaigns if c["severity"] == "high"]
        if high:
            message = f"Обнаружено {len(high)} CPL кампаний с низкой маржой (<10%)\n\n"
            message += "Требуют внимания:\n"

            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"margin {campaign['margin']:.2f}$ "
                message += f"({campaign['margin_percent']:.1f}%)\n"

            alerts.append({
                "type": "cpl_margin_high",
                "severity": "high",
                "message": message,
                "recommended_action": "Оптимизируйте источники трафика или пересмотрите ценообразование",
                "campaigns_count": len(high),
                "avg_margin_percent": round(sum(c["margin_percent"] for c in high) / len(high), 1)
            })

        return alerts
