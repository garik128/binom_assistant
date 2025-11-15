"""
Модуль обнаружения выгорания источников трафика
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


class SourceFatigueDetector(BaseModule):
    """
    Детектор выгорания источников трафика.

    Определяет выгорание источников по признакам:
    - Рост CPC > cpc_growth_threshold (по умолчанию 40%)
    - Снижение CR при стабильном или растущем трафике

    Критерии:
    - CPC growth > cpc_growth_threshold
    - CR падает (cr_drop > 0)
    - Минимум min_clicks кликов в обоих периодах
    - Сравнение текущего и предыдущего периодов
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="source_fatigue_detector",
            name="Выгорание источника",
            category="problem_detection",
            description="Определяет выгорание источников трафика",
            detailed_description="Модуль определяет выгорание источников трафика (усталость аудитории или креативов) по росту CPC и падению CR.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["fatigue", "source", "cpc", "cr", "traffic"]
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
                "cpc_growth_threshold": 40,  # рост CPC > 40%
                "cr_drop_threshold": 20,  # падение CR > 20% (не используется в фильтре, но полезен)
                "min_clicks": 100,  # минимум кликов за период
                "severity_critical_cpc_growth": 50,  # рост CPC для critical severity (%)
                "severity_high_cpc_growth": 40  # рост CPC для high severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа (текущий и предыдущий период)",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "cpc_growth_threshold": {
                "label": "Порог роста CPC (%)",
                "description": "Минимальный рост CPC для определения выгорания",
                "type": "number",
                "min": 10,
                "max": 100,
                "default": 40
            },
            "cr_drop_threshold": {
                "label": "Порог падения CR (%)",
                "description": "Информационный порог падения CR (не используется в фильтре)",
                "type": "number",
                "min": 5,
                "max": 100,
                "default": 20
            },
            "min_clicks": {
                "label": "Минимум кликов за период",
                "description": "Минимальное количество кликов в обоих периодах",
                "type": "number",
                "min": 50,
                "max": 10000,
                "default": 100
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "cpc_growth",
            "metric_label": "Рост CPC",
            "metric_unit": "%",
            "description": "Пороги критичности на основе роста CPC",
            "thresholds": {
                "severity_critical_cpc_growth": {
                    "label": "Критичный рост CPC (%)",
                    "description": "Рост CPC выше этого значения считается критичным",
                    "type": "number",
                    "min": 40,
                    "max": 100,
                    "step": 5,
                    "default": 50
                },
                "severity_high_cpc_growth": {
                    "label": "Высокий рост CPC (%)",
                    "description": "Рост CPC выше этого значения (но ниже критичного) считается высокой важности",
                    "type": "number",
                    "min": 20,
                    "max": 80,
                    "step": 5,
                    "default": 40
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "CPC growth > 50%, CR падает"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "CPC growth > 40%, CR падает"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ выгорания источников.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с признаками выгорания
        """
        # Получение параметров
        days = config.params.get("days", 7)
        cpc_growth_threshold = config.params.get("cpc_growth_threshold", 40)
        cr_drop_threshold = config.params.get("cr_drop_threshold", 20)
        min_clicks = config.params.get("min_clicks", 100)

        # Получение настраиваемых порогов severity
        severity_critical_cpc_growth = config.params.get("severity_critical_cpc_growth", 50)
        severity_high_cpc_growth = config.params.get("severity_high_cpc_growth", 40)

        # Периоды анализа
        # Текущий период: последние days дней (включая сегодня)
        current_date_to = datetime.now().date()
        current_date_from = current_date_to - timedelta(days=days - 1)

        # Предыдущий период: предыдущие days дней
        previous_date_to = current_date_from - timedelta(days=1)
        previous_date_from = previous_date_to - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем данные для текущего периода
            current_query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                func.sum(CampaignStatsDaily.cost).label('total_cost'),
                func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
                func.sum(CampaignStatsDaily.leads).label('total_leads')
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= current_date_from,
                CampaignStatsDaily.date <= current_date_to
            ).group_by(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name
            )

            current_results = current_query.all()

            # Получаем данные для предыдущего периода
            previous_query = session.query(
                Campaign.internal_id,
                func.sum(CampaignStatsDaily.cost).label('total_cost'),
                func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
                func.sum(CampaignStatsDaily.leads).label('total_leads')
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= previous_date_from,
                CampaignStatsDaily.date <= previous_date_to
            ).group_by(
                Campaign.internal_id
            )

            previous_results = previous_query.all()

            # Создаем словарь для предыдущего периода
            previous_data = {}
            for row in previous_results:
                previous_data[row.internal_id] = {
                    "cost": float(row.total_cost) if row.total_cost else 0,
                    "clicks": row.total_clicks or 0,
                    "leads": row.total_leads or 0
                }

            # Обработка и поиск кампаний с выгоранием
            problem_campaigns = []
            total_campaigns_checked = 0
            critical_count = 0
            high_count = 0

            for row in current_results:
                campaign_id = row.internal_id

                # Текущий период
                current_cost = float(row.total_cost) if row.total_cost else 0
                current_clicks = row.total_clicks or 0
                current_leads = row.total_leads or 0

                # Предыдущий период
                if campaign_id not in previous_data:
                    continue

                prev_data = previous_data[campaign_id]
                previous_cost = prev_data["cost"]
                previous_clicks = prev_data["clicks"]
                previous_leads = prev_data["leads"]

                # Фильтрация: минимум кликов в обоих периодах
                if current_clicks < min_clicks or previous_clicks < min_clicks:
                    continue

                total_campaigns_checked += 1

                # Расчет CPC для обоих периодов
                current_cpc = current_cost / current_clicks if current_clicks > 0 else 0
                previous_cpc = previous_cost / previous_clicks if previous_clicks > 0 else 0

                # Расчет CR для обоих периодов
                current_cr = (current_leads / current_clicks * 100) if current_clicks > 0 else 0
                previous_cr = (previous_leads / previous_clicks * 100) if previous_clicks > 0 else 0

                # Расчет изменений
                # CPC growth = ((current_cpc - previous_cpc) / previous_cpc) * 100
                if previous_cpc > 0:
                    cpc_growth_percent = ((current_cpc - previous_cpc) / previous_cpc) * 100
                else:
                    cpc_growth_percent = 0

                # CR drop = ((previous_cr - current_cr) / previous_cr) * 100
                if previous_cr > 0:
                    cr_drop_percent = ((previous_cr - current_cr) / previous_cr) * 100
                else:
                    cr_drop_percent = 0

                # Изменение трафика (кликов)
                if previous_clicks > 0:
                    traffic_change_percent = ((current_clicks - previous_clicks) / previous_clicks) * 100
                else:
                    traffic_change_percent = 0

                # Проверка критериев выгорания:
                # CPC growth >= cpc_growth_threshold AND CR падает (cr_drop > 0)
                if cpc_growth_percent < cpc_growth_threshold:
                    continue

                if cr_drop_percent <= 0:
                    # CR не падает или растет
                    continue

                # Определение критичности на основе настраиваемых порогов
                # critical: CPC growth >= severity_critical_cpc_growth AND CR падает
                # high: CPC growth >= severity_high_cpc_growth AND CR падает
                if cpc_growth_percent >= severity_critical_cpc_growth:
                    severity = "critical"
                    severity_label = f"Критично (CPC >{severity_critical_cpc_growth}%, CR падает)"
                    critical_count += 1
                else:
                    severity = "high"
                    severity_label = f"Высокий (CPC >{severity_high_cpc_growth}%, CR падает)"
                    high_count += 1

                problem_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": row.binom_id,
                    "name": row.current_name,
                    "group": row.group_name or "Без группы",
                    "current_cpc": round(current_cpc, 3),
                    "previous_cpc": round(previous_cpc, 3),
                    "cpc_growth_percent": round(cpc_growth_percent, 1),
                    "current_cr": round(current_cr, 2),
                    "previous_cr": round(previous_cr, 2),
                    "cr_drop_percent": round(cr_drop_percent, 1),
                    "current_clicks": current_clicks,
                    "previous_clicks": previous_clicks,
                    "traffic_change_percent": round(traffic_change_percent, 1),
                    "severity": severity,
                    "severity_label": severity_label
                })

            # Сортировка: сначала с наибольшим ростом CPC
            problem_campaigns.sort(key=lambda x: x["cpc_growth_percent"], reverse=True)

            return {
                "campaigns": problem_campaigns,
                "summary": {
                    "total_problems": len(problem_campaigns),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "total_checked": total_campaigns_checked
                },
                "periods": {
                    "days": days,
                    "current": {
                        "date_from": current_date_from.isoformat(),
                        "date_to": current_date_to.isoformat()
                    },
                    "previous": {
                        "date_from": previous_date_from.isoformat(),
                        "date_to": previous_date_to.isoformat()
                    }
                },
                "params": {
                    "cpc_growth_threshold": cpc_growth_threshold,
                    "cr_drop_threshold": cr_drop_threshold,
                    "min_clicks": min_clicks
                },
                "thresholds": {
                    "severity_critical_cpc_growth": severity_critical_cpc_growth,
                    "severity_high_cpc_growth": severity_high_cpc_growth
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
            "id": "source_fatigue_severity_chart",
            "type": "pie",
            "data": {
                "labels": ["Критично (CPC >50%)", "Высокий (CPC >40%)"],
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

        # График роста CPC для топ-10
        top_10 = problem_campaigns[:10]
        charts.append({
            "id": "cpc_growth_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Рост CPC (%)",
                    "data": [c["cpc_growth_percent"] for c in top_10],
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
                        "text": "Топ-10 кампаний по росту CPC"
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

        # График падения CR для топ-10
        charts.append({
            "id": "cr_drop_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Падение CR (%)",
                    "data": [c["cr_drop_percent"] for c in top_10],
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
                        "text": "Топ-10 кампаний по падению CR"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Падение CR (%)"
                        }
                    }
                }
            }
        })

        # График сравнения CPC (текущий vs предыдущий)
        charts.append({
            "id": "cpc_comparison_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "Предыдущий CPC",
                        "data": [c["previous_cpc"] for c in top_10],
                        "backgroundColor": "rgba(54, 162, 235, 0.6)",
                        "borderColor": "rgba(54, 162, 235, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "Текущий CPC",
                        "data": [c["current_cpc"] for c in top_10],
                        "backgroundColor": "rgba(255, 99, 132, 0.6)",
                        "borderColor": "rgba(255, 99, 132, 1)",
                        "borderWidth": 1
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Сравнение CPC (текущий vs предыдущий)"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "CPC ($)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для выгорания источников.
        """
        problem_campaigns = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not problem_campaigns:
            return alerts

        # Общий алерт с краткой сводкой
        critical_count = summary.get("critical_count", 0)
        high_count = summary.get("high_count", 0)

        message = f"Обнаружено {len(problem_campaigns)} кампаний с признаками выгорания источников\n\n"

        # Критичные (CPC growth > 50%)
        if critical_count > 0:
            critical = [c for c in problem_campaigns if c["severity"] == "critical"]
            message += f"Критичные ({critical_count} кампаний, рост CPC >50%):\n"
            for i, campaign in enumerate(critical[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CPC вырос на {campaign['cpc_growth_percent']:.1f}% "
                message += f"(${campaign['previous_cpc']:.3f} -> ${campaign['current_cpc']:.3f}), "
                message += f"CR упал на {campaign['cr_drop_percent']:.1f}%\n"

        # Высокий уровень (CPC growth > threshold)
        if high_count > 0:
            high = [c for c in problem_campaigns if c["severity"] == "high"]
            message += f"\nВысокий уровень ({high_count} кампаний):\n"
            for i, campaign in enumerate(high[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CPC вырос на {campaign['cpc_growth_percent']:.1f}% "
                message += f"(${campaign['previous_cpc']:.3f} -> ${campaign['current_cpc']:.3f}), "
                message += f"CR упал на {campaign['cr_drop_percent']:.1f}%\n"

        severity = "critical" if critical_count > 0 else "high"

        alerts.append({
            "type": "source_fatigue",
            "severity": severity,
            "message": message,
            "recommended_action": "Обновите креативы, смените таргетинг или источник трафика. Рассмотрите снижение ставок или паузу кампании.",
            "campaigns_count": len(problem_campaigns),
            "critical_count": critical_count,
            "high_count": high_count
        })

        return alerts
