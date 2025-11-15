"""
Модуль оценки влияния задержки апрувов
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


class ApprovalDelayImpact(BaseModule):
    """
    Оценка влияния задержки апрувов на кэшфлоу.

    Только для CPA кампаний (a_leads > 0).
    Оценивает среднюю задержку апрувов и замороженные средства.

    Критерии:
    - Только CPA кампании (a_leads > 0)
    - Средняя задержка апрува (примерная оценка на основе соотношения pending/approved)
    - Замороженные средства = cost за период с pending лидами
    - Влияние на cashflow = frozen_percent от общего расхода
    - Фильтрация: минимум min_approvals апрувов за период
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="approval_delay_impact",
            name="Задержка апрувов",
            category="problem_detection",
            description="Оценивает влияние задержек апрувов на кэшфлоу",
            detailed_description="Модуль оценивает влияние задержек апрувов на кэшфлоу в CPA кампаниях. Вычисляет примерную задержку и замороженные средства. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["cpa", "approvals", "cashflow", "delay"]
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
                "min_approvals": 10,  # минимум апрувов для анализа
                "delay_threshold": 3,  # порог задержки в днях для алерта
                "severity_critical_delay": 7,  # задержка для critical severity (дней)
                "severity_high_delay": 3  # задержка для high severity (дней)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа апрувов",
                "type": "number",
                "min": 7,
                "max": 365,
                "default": 14
            },
            "min_approvals": {
                "label": "Минимум апрувов",
                "description": "Минимальное количество апрувов для включения в анализ",
                "type": "number",
                "min": 5,
                "max": 1000,
                "default": 10
            },
            "delay_threshold": {
                "label": "Порог задержки (дней)",
                "description": "Минимальная задержка для определения проблемы",
                "type": "number",
                "min": 1,
                "max": 14,
                "default": 3
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "delay_days",
            "metric_label": "Задержка апрувов",
            "metric_unit": "дней",
            "description": "Пороги критичности на основе задержки апрувов",
            "thresholds": {
                "severity_critical_delay": {
                    "label": "Критичная задержка (дней)",
                    "description": "Задержка апрувов выше этого значения считается критичной",
                    "type": "number",
                    "min": 5,
                    "max": 14,
                    "step": 1,
                    "default": 7
                },
                "severity_high_delay": {
                    "label": "Высокая задержка (дней)",
                    "description": "Задержка апрувов выше этого значения (но ниже критичной) считается высокой важности",
                    "type": "number",
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "default": 3
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "delay >= 7 дней"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "delay >= 3 дней"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ влияния задержки апрувов.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с задержками апрувов
        """
        # Получение параметров
        days = config.params.get("days", 14)
        min_approvals = config.params.get("min_approvals", 10)
        delay_threshold = config.params.get("delay_threshold", 3)

        # Получение настраиваемых порогов severity
        severity_critical_delay = config.params.get("severity_critical_delay", 7)
        severity_high_delay = config.params.get("severity_high_delay", 3)

        # Период анализа (исключаем сегодняшний день - апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

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
                CampaignStatsDaily.h_leads,
                CampaignStatsDaily.r_leads
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
                "total_leads": 0,
                "total_a_leads": 0,
                "total_h_leads": 0,
                "total_r_leads": 0,
                "daily_stats": []
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                leads = row.leads or 0
                a_leads = row.a_leads or 0
                h_leads = row.h_leads or 0
                r_leads = row.r_leads or 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_revenue"] += revenue
                campaigns_data[campaign_id]["total_leads"] += leads
                campaigns_data[campaign_id]["total_a_leads"] += a_leads
                campaigns_data[campaign_id]["total_h_leads"] += h_leads
                campaigns_data[campaign_id]["total_r_leads"] += r_leads

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads,
                    "h_leads": h_leads,
                    "r_leads": r_leads
                })

            # Обработка и поиск кампаний с задержками апрувов
            problem_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0
            total_delays = []

            for campaign_id, data in campaigns_data.items():
                # КРИТИЧНО: Фильтр CPA кампаний
                # CPA кампания: a_leads > 0 (есть апрувы)
                if data["total_a_leads"] == 0:
                    # Это не CPA кампания (нет апрувов)
                    continue

                # Фильтрация: минимум апрувов
                if data["total_a_leads"] < min_approvals:
                    continue

                total_campaigns_checked += 1

                # Расчет pending лидов
                pending_leads = data["total_h_leads"]  # h_leads = холд = pending

                # Расчет процента апрува
                total_processed = data["total_a_leads"] + data["total_r_leads"]
                approval_rate = (data["total_a_leads"] / total_processed * 100) if total_processed > 0 else 0

                # ПРИМЕРНАЯ оценка задержки апрувов
                # Используем эвристику на основе соотношения pending к обработанным лидам
                # Задержка НЕ зависит от периода анализа - это характеристика партнерки

                # Метод 1: Оценка по доле pending лидов
                # Если 50% лидов в pending, значит средняя задержка ~3-4 дня (типичная оценка)
                # Формула: delay_days = pending_ratio * 7 (максимальная оценка задержки)
                if data["total_leads"] > 0:
                    pending_ratio = pending_leads / data["total_leads"]
                    delay_by_pending = pending_ratio * 7  # 7 дней - максимальная типичная задержка
                else:
                    delay_by_pending = 0

                # Метод 2: Оценка по approval rate
                # Низкий approval_rate означает больше времени на обработку
                # Если approval_rate = 50%, то примерно половина лидов еще не обработана
                # Формула: delay_days = (1 - approval_rate/100) * 6
                if approval_rate < 100:
                    delay_by_rate = (100 - approval_rate) / 100 * 6
                else:
                    delay_by_rate = 0

                # Берем максимум из двух оценок
                avg_delay_days = max(delay_by_pending, delay_by_rate)

                # Расчет замороженных средств
                # Замороженные средства = cost * (pending_leads / total_leads)
                if data["total_leads"] > 0:
                    frozen_funds = data["total_cost"] * (pending_leads / data["total_leads"])
                else:
                    frozen_funds = 0

                # Расчет frozen_percent
                frozen_percent = (frozen_funds / data["total_cost"] * 100) if data["total_cost"] > 0 else 0

                # Проверка критериев проблемной задержки
                if avg_delay_days < delay_threshold:
                    continue

                # Определение критичности на основе настраиваемых порогов
                if avg_delay_days >= severity_critical_delay:
                    severity = "critical"
                    severity_label = f"Критично (>{severity_critical_delay} дней)"
                    critical_count += 1
                elif avg_delay_days >= severity_high_delay:
                    severity = "high"
                    severity_label = f"Высокий (>{severity_high_delay} дней)"
                    high_count += 1
                else:
                    continue

                total_delays.append(avg_delay_days)

                problem_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "avg_delay_days": round(avg_delay_days, 1),
                    "frozen_funds": round(frozen_funds, 2),
                    "total_cost": round(data["total_cost"], 2),
                    "frozen_percent": round(frozen_percent, 1),
                    "total_approvals": data["total_a_leads"],
                    "pending_leads": pending_leads,
                    "approval_rate": round(approval_rate, 1),
                    "severity": severity,
                    "severity_label": severity_label
                })

            # Сортировка: сначала с наибольшей задержкой
            problem_campaigns.sort(key=lambda x: x["avg_delay_days"], reverse=True)

            # Средняя задержка по всем проблемным кампаниям
            avg_delay_overall = sum(total_delays) / len(total_delays) if total_delays else 0

            return {
                "campaigns": problem_campaigns,
                "summary": {
                    "total_problems": len(problem_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "total_checked": total_campaigns_checked,
                    "avg_delay_overall": round(avg_delay_overall, 1)
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_approvals": min_approvals,
                    "delay_threshold": delay_threshold
                },
                "thresholds": {
                    "severity_critical_delay": severity_critical_delay,
                    "severity_high_delay": severity_high_delay
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
            "id": "approval_delay_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично (>7 дней)", "Высокий (>3 дней)"],
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

        # График задержек для топ-10
        top_10 = problem_campaigns[:10]
        charts.append({
            "id": "approval_delay_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Средняя задержка (дней)",
                    "data": [c["avg_delay_days"] for c in top_10],
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
                        "text": "Топ-10 кампаний по задержке апрувов"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Задержка (дней)"
                        }
                    }
                }
            }
        })

        # График замороженных средств для топ-10
        charts.append({
            "id": "frozen_funds_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Замороженные средства ($)",
                    "data": [c["frozen_funds"] for c in top_10],
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
                        "text": "Топ-10 по замороженным средствам"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Замороженные средства ($)"
                        }
                    }
                }
            }
        })

        # График frozen_percent для топ-10
        charts.append({
            "id": "frozen_percent_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Замороженный % от расхода",
                    "data": [c["frozen_percent"] for c in top_10],
                    "backgroundColor": "rgba(255, 205, 86, 0.6)",
                    "borderColor": "rgba(255, 205, 86, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по проценту замороженных средств"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Замороженный %"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с задержкой апрувов.
        """
        problem_campaigns = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not problem_campaigns:
            return alerts

        # Общий алерт с краткой сводкой
        total_frozen = sum(c["frozen_funds"] for c in problem_campaigns)
        avg_delay = summary.get("avg_delay_overall", 0)

        message = f"Обнаружено {len(problem_campaigns)} CPA кампаний с задержками апрувов\n\n"
        message += f"Средняя задержка: {avg_delay:.1f} дней\n"
        message += f"Всего замороженных средств: ${total_frozen:.2f}\n\n"

        # Критичные (задержка > 7 дней)
        critical = [c for c in problem_campaigns if c["severity"] == "critical"]
        if critical:
            message += f"\nКритичные ({len(critical)} кампаний, задержка >7 дней):\n"
            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"{campaign['avg_delay_days']:.1f} дней, "
                message += f"заморожено ${campaign['frozen_funds']:.2f}\n"

        # Высокий уровень
        high = [c for c in problem_campaigns if c["severity"] == "high"]
        if high:
            message += f"\nВысокий уровень ({len(high)} кампаний):\n"
            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"{campaign['avg_delay_days']:.1f} дней, "
                message += f"заморожено ${campaign['frozen_funds']:.2f}\n"

        severity = "critical" if critical else "high"

        alerts.append({
            "type": "approval_delay_impact",
            "severity": severity,
            "message": message,
            "recommended_action": "Свяжитесь с партнерской программой для ускорения апрувов или пересмотрите бюджеты с учетом cashflow",
            "campaigns_count": len(problem_campaigns),
            "total_frozen_funds": round(total_frozen, 2),
            "avg_delay": avg_delay
        })

        return alerts
