"""
Модуль обнаружения неожиданных лидеров (Sudden Winner Detector)
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


class SuddenWinnerDetector(BaseModule):
    """
    Детектор неожиданных лидеров (Sudden Winner).

    Находит кампании с внезапным ростом эффективности:
    - Резкий рост ROI (более 50%)
    - Резкий рост CR (более 100%)
    - За короткий период (последние 3 дня vs предыдущие 7 дней)

    Критерии:
    - Рост ROI > roi_growth_threshold (по умолчанию 50%) ИЛИ
    - Рост CR > cr_growth_threshold (по умолчанию 100%)
    - Минимум min_clicks кликов в текущем периоде (по умолчанию 50)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="sudden_winner_detector",
            name="Неожиданный лидер",
            category="opportunities",
            description="Обнаруживает кампании с внезапным ростом эффективности",
            detailed_description="Модуль находит кампании с резким улучшением показателей более 50% за короткий период. Помогает быстро масштабировать успех.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["opportunities", "growth", "roi", "surge"]
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
                "recent_days": 3,  # период текущей активности
                "comparison_days": 7,  # период для сравнения
                "roi_growth_threshold": 50,  # рост ROI > 50%
                "cr_growth_threshold": 100,  # рост CR > 100%
                "min_clicks": 50  # минимум кликов в текущем периоде
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "recent_days": {
                "label": "Период текущей активности (дней)",
                "description": "Количество последних дней для оценки текущих показателей",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 3
            },
            "comparison_days": {
                "label": "Период для сравнения (дней)",
                "description": "Количество предыдущих дней для сравнения",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "roi_growth_threshold": {
                "label": "Порог роста ROI (%)",
                "description": "Минимальный процент роста ROI для определения победителя",
                "type": "number",
                "min": 20,
                "max": 200,
                "default": 50
            },
            "cr_growth_threshold": {
                "label": "Порог роста CR (%)",
                "description": "Минимальный процент роста CR для определения победителя",
                "type": "number",
                "min": 50,
                "max": 300,
                "default": 100
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов в текущем периоде",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 50
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ неожиданных лидеров.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с внезапным ростом
        """
        # Получение параметров
        recent_days = config.params.get("recent_days", 3)
        comparison_days = config.params.get("comparison_days", 7)
        roi_growth_threshold = config.params.get("roi_growth_threshold", 50)
        cr_growth_threshold = config.params.get("cr_growth_threshold", 100)
        min_clicks = config.params.get("min_clicks", 50)

        # Период анализа: последние (recent_days + comparison_days) дней
        total_days = recent_days + comparison_days
        date_from = datetime.now().date() - timedelta(days=total_days - 1)
        split_date = datetime.now().date() - timedelta(days=recent_days - 1)

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
                CampaignStatsDaily.leads,
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
                "recent_period": {
                    "clicks": 0,
                    "leads": 0,
                    "cost": 0,
                    "revenue": 0
                },
                "previous_period": {
                    "clicks": 0,
                    "leads": 0,
                    "cost": 0,
                    "revenue": 0
                }
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                clicks = row.clicks or 0
                leads = row.leads or 0
                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0

                # Разделяем на recent и previous периоды
                if row.date >= split_date:
                    # Recent период (последние recent_days дней)
                    campaigns_data[campaign_id]["recent_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["recent_period"]["leads"] += leads
                    campaigns_data[campaign_id]["recent_period"]["cost"] += cost
                    campaigns_data[campaign_id]["recent_period"]["revenue"] += revenue
                else:
                    # Previous период (предыдущие comparison_days дней)
                    campaigns_data[campaign_id]["previous_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["previous_period"]["leads"] += leads
                    campaigns_data[campaign_id]["previous_period"]["cost"] += cost
                    campaigns_data[campaign_id]["previous_period"]["revenue"] += revenue

            # Обработка и поиск внезапных победителей
            sudden_winners = []
            total_campaigns_checked = 0
            roi_surge_count = 0
            cr_surge_count = 0
            both_surge_count = 0

            for campaign_id, data in campaigns_data.items():
                recent = data["recent_period"]
                previous = data["previous_period"]

                # Фильтрация: минимум кликов в текущем периоде
                if recent["clicks"] < min_clicks:
                    continue

                # Фильтрация: должны быть данные в предыдущем периоде
                if previous["clicks"] == 0 or previous["cost"] == 0:
                    continue

                total_campaigns_checked += 1

                # Расчет ROI для текущего периода
                if recent["cost"] > 0:
                    recent_roi = ((recent["revenue"] - recent["cost"]) / recent["cost"]) * 100
                else:
                    recent_roi = 0

                # Расчет ROI для предыдущего периода
                if previous["cost"] > 0:
                    previous_roi = ((previous["revenue"] - previous["cost"]) / previous["cost"]) * 100
                else:
                    previous_roi = 0

                # Расчет CR для текущего периода
                recent_cr = (recent["leads"] / recent["clicks"] * 100) if recent["clicks"] > 0 else 0

                # Расчет CR для предыдущего периода
                previous_cr = (previous["leads"] / previous["clicks"] * 100) if previous["clicks"] > 0 else 0

                # Расчет роста ROI
                # Используем правильную формулу без abs() для корректной обработки отрицательных ROI
                if previous_roi != 0:
                    roi_growth_percent = ((recent_roi - previous_roi) / previous_roi) * 100
                else:
                    # Если предыдущий ROI был 0, а текущий положительный - это рост
                    if recent_roi > 0:
                        roi_growth_percent = 999  # Очень большой рост
                    else:
                        roi_growth_percent = 0

                # Расчет роста CR
                if previous_cr > 0:
                    cr_growth_percent = ((recent_cr - previous_cr) / previous_cr) * 100
                else:
                    # Если предыдущий CR был 0, а текущий положительный - это рост
                    if recent_cr > 0:
                        cr_growth_percent = 999  # Очень большой рост
                    else:
                        cr_growth_percent = 0

                # Проверка критериев внезапного победителя
                is_roi_surge = roi_growth_percent >= roi_growth_threshold
                is_cr_surge = cr_growth_percent >= cr_growth_threshold

                if not (is_roi_surge or is_cr_surge):
                    continue

                # Определение типа роста
                if is_roi_surge and is_cr_surge:
                    win_type = "both"
                    both_surge_count += 1
                elif is_roi_surge:
                    win_type = "roi_surge"
                    roi_surge_count += 1
                else:
                    win_type = "cr_surge"
                    cr_surge_count += 1

                sudden_winners.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "recent_roi": round(recent_roi, 1),
                    "previous_roi": round(previous_roi, 1),
                    "roi_growth_percent": round(roi_growth_percent, 1),
                    "recent_cr": round(recent_cr, 2),
                    "previous_cr": round(previous_cr, 2),
                    "cr_growth_percent": round(cr_growth_percent, 1),
                    "recent_clicks": recent["clicks"],
                    "recent_revenue": round(recent["revenue"], 2),
                    "recent_cost": round(recent["cost"], 2),
                    "win_type": win_type
                })

            # Сортировка: сначала both, потом roi_surge, потом cr_surge
            # Внутри каждой группы по roi_growth_percent DESC
            sudden_winners.sort(key=lambda x: (
                0 if x["win_type"] == "both" else (1 if x["win_type"] == "roi_surge" else 2),
                -x["roi_growth_percent"]
            ))

            return {
                "campaigns": sudden_winners,
                "summary": {
                    "total_winners": len(sudden_winners),
                    "roi_surge": roi_surge_count,
                    "cr_surge": cr_surge_count,
                    "both": both_surge_count,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "recent_days": recent_days,
                    "comparison_days": comparison_days,
                    "date_from": date_from.isoformat(),
                    "split_date": split_date.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "roi_growth_threshold": roi_growth_threshold,
                    "cr_growth_threshold": cr_growth_threshold,
                    "min_clicks": min_clicks
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        sudden_winners = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})

        if not sudden_winners:
            return []

        charts = []

        # График распределения по типу роста
        charts.append({
            "id": "winner_type_chart",
            "type": "pie",
            "data": {
                "labels": ["Рост ROI и CR", "Только рост ROI", "Только рост CR"],
                "datasets": [{
                    "data": [
                        summary.get("both", 0),
                        summary.get("roi_surge", 0),
                        summary.get("cr_surge", 0)
                    ],
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.8)",
                        "rgba(23, 162, 184, 0.8)",
                        "rgba(255, 193, 7, 0.8)"
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение по типу роста"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График роста ROI для топ-10
        top_10 = sudden_winners[:10]
        charts.append({
            "id": "winner_roi_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "Предыдущий ROI (%)",
                        "data": [c["previous_roi"] for c in top_10],
                        "backgroundColor": "rgba(108, 117, 125, 0.6)",
                        "borderColor": "rgba(108, 117, 125, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "Текущий ROI (%)",
                        "data": [c["recent_roi"] for c in top_10],
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
                        "text": "Топ-10 по росту ROI"
                    }
                },
                "scales": {
                    "y": {
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        }
                    }
                }
            }
        })

        # График роста CR для топ-10
        charts.append({
            "id": "winner_cr_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "Предыдущий CR (%)",
                        "data": [c["previous_cr"] for c in top_10],
                        "backgroundColor": "rgba(108, 117, 125, 0.6)",
                        "borderColor": "rgba(108, 117, 125, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "Текущий CR (%)",
                        "data": [c["recent_cr"] for c in top_10],
                        "backgroundColor": "rgba(23, 162, 184, 0.6)",
                        "borderColor": "rgba(23, 162, 184, 1)",
                        "borderWidth": 1
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Топ-10 по росту CR"
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

        # График процента роста ROI для топ-10
        charts.append({
            "id": "winner_roi_growth_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Рост ROI (%)",
                    "data": [c["roi_growth_percent"] for c in top_10],
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
                        "text": "Топ-10 по проценту роста ROI"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Рост (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для внезапных победителей.
        """
        sudden_winners = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not sudden_winners:
            return alerts

        # Общий алерт с краткой сводкой
        total_winners = summary.get("total_winners", 0)
        both_count = summary.get("both", 0)
        roi_surge_count = summary.get("roi_surge", 0)
        cr_surge_count = summary.get("cr_surge", 0)

        message = f"Обнаружено {total_winners} внезапных победителей\n\n"

        # Рост и ROI и CR
        if both_count > 0:
            both = [c for c in sudden_winners if c["win_type"] == "both"]
            message += f"Рост ROI и CR ({both_count} кампаний):\n"
            for i, campaign in enumerate(both[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['previous_roi']:.1f}% -> {campaign['recent_roi']:.1f}% "
                message += f"(+{campaign['roi_growth_percent']:.1f}%), "
                message += f"CR {campaign['previous_cr']:.2f}% -> {campaign['recent_cr']:.2f}% "
                message += f"(+{campaign['cr_growth_percent']:.1f}%)\n"
            message += "\n"

        # Только рост ROI
        if roi_surge_count > 0:
            roi_surge = [c for c in sudden_winners if c["win_type"] == "roi_surge"]
            message += f"Только рост ROI ({roi_surge_count} кампаний):\n"
            for i, campaign in enumerate(roi_surge[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['previous_roi']:.1f}% -> {campaign['recent_roi']:.1f}% "
                message += f"(+{campaign['roi_growth_percent']:.1f}%)\n"
            message += "\n"

        # Только рост CR
        if cr_surge_count > 0:
            cr_surge = [c for c in sudden_winners if c["win_type"] == "cr_surge"]
            message += f"Только рост CR ({cr_surge_count} кампаний):\n"
            for i, campaign in enumerate(cr_surge[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"CR {campaign['previous_cr']:.2f}% -> {campaign['recent_cr']:.2f}% "
                message += f"(+{campaign['cr_growth_percent']:.1f}%)\n"

        severity = "medium"  # Это возможности, а не проблемы

        alerts.append({
            "type": "sudden_winner",
            "severity": severity,
            "message": message,
            "recommended_action": "Рассмотрите возможность быстрого масштабирования этих кампаний. Увеличьте бюджеты аккуратно, отслеживая сохранение показателей",
            "total_winners": total_winners,
            "both": both_count,
            "roi_surge": roi_surge_count,
            "cr_surge": cr_surge_count
        })

        return alerts
