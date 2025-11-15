"""
Модуль обнаружения прорыва после стагнации (Breakout Alert)
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


class BreakoutAlert(BaseModule):
    """
    Детектор прорывов после стагнации (Breakout Alert).

    Находит кампании, которые долго показывали средние результаты,
    но вдруг пробили потолок:
    - Период стагнации с ROI в диапазоне ±stagnation_threshold%
    - Резкий рост ROI > breakout_threshold% за recent_days
    - Объемы трафика не изменились значительно
    - Подтверждение положительной динамикой CR

    Критерии:
    - Стагнация: std_dev(ROI) / mean(ROI) < stagnation_threshold / 100
    - ROI growth >= breakout_threshold (по умолчанию 30%)
    - abs(traffic_change) <= traffic_change_limit (по умолчанию 50%)
    - recent_clicks >= min_clicks (по умолчанию 50)
    - cr_confirmed = recent_cr > stagnation_cr
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="breakout_alert",
            name="Прорыв",
            category="opportunities",
            description="Находит кампании с прорывом после периода стагнации",
            detailed_description="Модуль находит кампании, которые долго показывали средние результаты, но вдруг резко улучшили показатели. Помогает выявить перспективные изменения и быстро масштабировать успех.",
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["opportunities", "breakout", "roi", "growth"]
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
                "stagnation_days": 10,  # период стагнации
                "stagnation_threshold": 20,  # диапазон стагнации ROI ±20%
                "recent_days": 3,  # период для определения прорыва
                "breakout_threshold": 30,  # рост ROI > 30%
                "traffic_change_limit": 50,  # макс. изменение кликов %
                "min_clicks": 50  # минимум кликов в recent периоде
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "stagnation_days": {
                "label": "Период стагнации (дней)",
                "description": "Количество дней стабильных показателей перед прорывом",
                "type": "number",
                "min": 5,
                "max": 365,
                "default": 10
            },
            "stagnation_threshold": {
                "label": "Диапазон стагнации ROI (±%)",
                "description": "Максимальное отклонение ROI в период стагнации",
                "type": "number",
                "min": 10,
                "max": 50,
                "default": 20
            },
            "recent_days": {
                "label": "Период прорыва (дней)",
                "description": "Количество последних дней для определения прорыва",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 3
            },
            "breakout_threshold": {
                "label": "Порог прорыва ROI (%)",
                "description": "Минимальный процент роста ROI для определения прорыва",
                "type": "number",
                "min": 20,
                "max": 100,
                "default": 30
            },
            "traffic_change_limit": {
                "label": "Максимальное изменение трафика (%)",
                "description": "Максимально допустимое изменение кликов между периодами",
                "type": "number",
                "min": 20,
                "max": 100,
                "default": 50
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов в период прорыва",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 50
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ прорывов после стагнации.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с прорывом
        """
        # Получение параметров
        stagnation_days = config.params.get("stagnation_days", 10)
        stagnation_threshold = config.params.get("stagnation_threshold", 20)
        recent_days = config.params.get("recent_days", 3)
        breakout_threshold = config.params.get("breakout_threshold", 30)
        traffic_change_limit = config.params.get("traffic_change_limit", 50)
        min_clicks = config.params.get("min_clicks", 50)

        # Период анализа: последние (stagnation_days + recent_days) дней
        total_days = stagnation_days + recent_days
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
                "stagnation_period": {
                    "clicks": 0,
                    "leads": 0,
                    "cost": 0,
                    "revenue": 0,
                    "daily_roi": []
                },
                "recent_period": {
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

                # Разделяем на stagnation и recent периоды
                if row.date < split_date:
                    # Stagnation период
                    campaigns_data[campaign_id]["stagnation_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["stagnation_period"]["leads"] += leads
                    campaigns_data[campaign_id]["stagnation_period"]["cost"] += cost
                    campaigns_data[campaign_id]["stagnation_period"]["revenue"] += revenue

                    # Собираем дневные ROI для анализа стагнации
                    if cost > 0:
                        daily_roi = ((revenue - cost) / cost) * 100
                        campaigns_data[campaign_id]["stagnation_period"]["daily_roi"].append(daily_roi)
                else:
                    # Recent период (прорыв)
                    campaigns_data[campaign_id]["recent_period"]["clicks"] += clicks
                    campaigns_data[campaign_id]["recent_period"]["leads"] += leads
                    campaigns_data[campaign_id]["recent_period"]["cost"] += cost
                    campaigns_data[campaign_id]["recent_period"]["revenue"] += revenue

            # Обработка и поиск прорывов
            breakouts = []
            total_campaigns_checked = 0
            total_roi_growth_sum = 0

            for campaign_id, data in campaigns_data.items():
                stagnation = data["stagnation_period"]
                recent = data["recent_period"]

                # Фильтрация: минимум кликов в recent периоде
                if recent["clicks"] < min_clicks:
                    continue

                # Фильтрация: должны быть данные в стagnation периоде
                # Минимум 3 дня для статистической значимости
                if stagnation["cost"] == 0 or len(stagnation["daily_roi"]) < 3:
                    continue

                # Фильтрация: должны быть данные в recent периоде
                if recent["cost"] == 0:
                    continue

                total_campaigns_checked += 1

                # Расчет статистики ROI для stagnation периода
                stagnation_avg_roi = statistics.mean(stagnation["daily_roi"])
                stagnation_std_roi = statistics.stdev(stagnation["daily_roi"])

                # Проверка стагнации: CV (коэффициент вариации)
                # CV = std_dev / mean
                # CV корректен только для положительных средних значений
                if stagnation_avg_roi > 0:
                    stagnation_cv = stagnation_std_roi / stagnation_avg_roi
                else:
                    # Если средний ROI <= 0, то это не интересная кампания для opportunities
                    continue

                # Фильтрация: проверяем что это действительно стагнация
                # CV должен быть небольшим (стабильные показатели)
                stagnation_cv_threshold = stagnation_threshold / 100
                if stagnation_cv > stagnation_cv_threshold:
                    # Слишком большая волатильность, это не стагнация
                    continue

                # Расчет ROI для recent периода
                recent_roi = ((recent["revenue"] - recent["cost"]) / recent["cost"]) * 100

                # Расчет роста ROI
                # Используем правильную формулу без abs() для корректной обработки отрицательных ROI
                if stagnation_avg_roi != 0:
                    roi_growth_percent = ((recent_roi - stagnation_avg_roi) / stagnation_avg_roi) * 100
                else:
                    # Если предыдущий ROI был 0, а текущий положительный - это прорыв
                    if recent_roi > 0:
                        roi_growth_percent = 999  # Очень большой рост
                    else:
                        roi_growth_percent = 0

                # Фильтрация: рост ROI должен быть >= breakout_threshold
                if roi_growth_percent < breakout_threshold:
                    continue

                # Расчет изменения трафика
                if stagnation["clicks"] > 0:
                    traffic_change_percent = ((recent["clicks"] - stagnation["clicks"]) / stagnation["clicks"]) * 100
                else:
                    traffic_change_percent = 100  # Если не было трафика, то изменение 100%

                # Фильтрация: изменение трафика не должно быть слишком большим
                if abs(traffic_change_percent) > traffic_change_limit:
                    continue

                # Расчет CR для stagnation периода
                stagnation_cr = (stagnation["leads"] / stagnation["clicks"] * 100) if stagnation["clicks"] > 0 else 0

                # Расчет CR для recent периода
                recent_cr = (recent["leads"] / recent["clicks"] * 100) if recent["clicks"] > 0 else 0

                # Проверка подтверждения CR (CR должен расти)
                cr_confirmed = recent_cr > stagnation_cr

                # Фильтрация: CR должен быть подтвержден
                if not cr_confirmed:
                    continue

                total_roi_growth_sum += roi_growth_percent

                breakouts.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "stagnation_avg_roi": round(stagnation_avg_roi, 1),
                    "stagnation_std_roi": round(stagnation_std_roi, 2),
                    "recent_roi": round(recent_roi, 1),
                    "roi_growth_percent": round(roi_growth_percent, 1),
                    "stagnation_clicks": stagnation["clicks"],
                    "recent_clicks": recent["clicks"],
                    "traffic_change_percent": round(traffic_change_percent, 1),
                    "stagnation_cr": round(stagnation_cr, 2),
                    "recent_cr": round(recent_cr, 2),
                    "cr_confirmed": cr_confirmed
                })

            # Сортировка: по roi_growth_percent DESC
            breakouts.sort(key=lambda x: -x["roi_growth_percent"])

            return {
                "campaigns": breakouts,
                "summary": {
                    "total_breakouts": len(breakouts),
                    "avg_roi_growth": round(total_roi_growth_sum / len(breakouts), 1) if breakouts else 0,
                    "total_checked": total_campaigns_checked
                },
                "period": {
                    "stagnation_days": stagnation_days,
                    "recent_days": recent_days,
                    "date_from": date_from.isoformat(),
                    "split_date": split_date.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "stagnation_threshold": stagnation_threshold,
                    "breakout_threshold": breakout_threshold,
                    "traffic_change_limit": traffic_change_limit,
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
        breakouts = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})

        if not breakouts:
            return []

        charts = []

        # График распределения по росту ROI
        # Группируем по диапазонам: >100%, 50-100%, 30-50%
        roi_growth_ranges = {">100%": 0, "50-100%": 0, "30-50%": 0}
        for c in breakouts:
            roi_growth = c["roi_growth_percent"]
            if roi_growth > 100:
                roi_growth_ranges[">100%"] += 1
            elif roi_growth >= 50:
                roi_growth_ranges["50-100%"] += 1
            else:
                roi_growth_ranges["30-50%"] += 1

        charts.append({
            "id": "breakout_distribution_chart",
            "type": "pie",
            "data": {
                "labels": [">100% (сильный)", "50-100% (средний)", "30-50% (умеренный)"],
                "datasets": [{
                    "data": [
                        roi_growth_ranges[">100%"],
                        roi_growth_ranges["50-100%"],
                        roi_growth_ranges["30-50%"]
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
                        "text": "Распределение прорывов по силе роста ROI"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График ROI до и после прорыва для топ-10
        top_10 = breakouts[:10]
        charts.append({
            "id": "breakout_roi_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [
                    {
                        "label": "ROI в период стагнации (%)",
                        "data": [c["stagnation_avg_roi"] for c in top_10],
                        "backgroundColor": "rgba(108, 117, 125, 0.6)",
                        "borderColor": "rgba(108, 117, 125, 1)",
                        "borderWidth": 1
                    },
                    {
                        "label": "ROI после прорыва (%)",
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
                        "text": "Топ-10 прорывов: ROI до и после"
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

        # График роста ROI для топ-10
        charts.append({
            "id": "breakout_growth_chart",
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
                        "text": "Топ-10 по росту ROI"
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

        # График изменения трафика для топ-10
        charts.append({
            "id": "breakout_traffic_chart",
            "type": "bar",
            "data": {
                "labels": [f"{c['name'][:20]}..." if len(c['name']) > 20 else c['name'] for c in top_10],
                "datasets": [{
                    "label": "Изменение трафика (%)",
                    "data": [c["traffic_change_percent"] for c in top_10],
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.6)" if abs(c["traffic_change_percent"]) < 20 else
                        "rgba(23, 162, 184, 0.6)" if abs(c["traffic_change_percent"]) < 30 else
                        "rgba(255, 193, 7, 0.6)"
                        for c in top_10
                    ],
                    "borderColor": [
                        "rgba(40, 167, 69, 1)" if abs(c["traffic_change_percent"]) < 20 else
                        "rgba(23, 162, 184, 1)" if abs(c["traffic_change_percent"]) < 30 else
                        "rgba(255, 193, 7, 1)"
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
                        "text": "Топ-10: изменение трафика (должно быть небольшим)"
                    }
                },
                "scales": {
                    "y": {
                        "title": {
                            "display": True,
                            "text": "Изменение (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для прорывов.
        """
        breakouts = raw_data.get("campaigns", [])
        summary = raw_data.get("summary", {})
        alerts = []

        if not breakouts:
            return alerts

        # Общий алерт с краткой сводкой
        total_breakouts = summary.get("total_breakouts", 0)
        avg_roi_growth = summary.get("avg_roi_growth", 0)

        message = f"Обнаружено {total_breakouts} прорывов после периода стагнации\n\n"
        message += f"Средний рост ROI: {avg_roi_growth:.1f}%\n\n"

        # Сильные прорывы (рост > 100%)
        strong_breakouts = [c for c in breakouts if c["roi_growth_percent"] > 100]
        if strong_breakouts:
            message += f"Сильные прорывы (рост ROI > 100%, {len(strong_breakouts)} кампаний):\n"
            for i, campaign in enumerate(strong_breakouts[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['stagnation_avg_roi']:.1f}% -> {campaign['recent_roi']:.1f}% "
                message += f"(+{campaign['roi_growth_percent']:.1f}%), "
                message += f"CR {campaign['stagnation_cr']:.2f}% -> {campaign['recent_cr']:.2f}%\n"
            message += "\n"

        # Средние прорывы (50% <= рост <= 100%)
        medium_breakouts = [c for c in breakouts if 50 <= c["roi_growth_percent"] <= 100]
        if medium_breakouts:
            message += f"Средние прорывы (рост ROI 50-100%, {len(medium_breakouts)} кампаний):\n"
            for i, campaign in enumerate(medium_breakouts[:3], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['stagnation_avg_roi']:.1f}% -> {campaign['recent_roi']:.1f}% "
                message += f"(+{campaign['roi_growth_percent']:.1f}%)\n"
            message += "\n"

        # Умеренные прорывы (30% <= рост < 50%)
        moderate_breakouts = [c for c in breakouts if 30 <= c["roi_growth_percent"] < 50]
        if moderate_breakouts:
            message += f"Умеренные прорывы (рост ROI 30-50%, {len(moderate_breakouts)} кампаний):\n"
            for i, campaign in enumerate(moderate_breakouts[:2], 1):
                message += f"{i}. {campaign['name']}: "
                message += f"ROI {campaign['stagnation_avg_roi']:.1f}% -> {campaign['recent_roi']:.1f}% "
                message += f"(+{campaign['roi_growth_percent']:.1f}%)\n"

        severity = "medium"  # Это возможности, а не проблемы

        alerts.append({
            "type": "breakout_alert",
            "severity": severity,
            "message": message,
            "recommended_action": "Рассмотрите возможность быстрого масштабирования этих кампаний. Прорыв после стагнации может указывать на позитивные изменения в воронке или аудитории",
            "total_breakouts": total_breakouts,
            "avg_roi_growth": round(avg_roi_growth, 1),
            "strong_count": len(strong_breakouts),
            "medium_count": len(medium_breakouts),
            "moderate_count": len(moderate_breakouts)
        })

        return alerts
