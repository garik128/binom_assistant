"""
Модуль сегментации по эффективности (Performance Segmenter)
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


class PerformanceSegmenter(BaseModule):
    """
    Сегментация кампаний по эффективности.

    Разделение кампаний на топ/средние/слабые для применения разных стратегий управления.
    Автоматическое распределение по квартилям.

    Логика сегментации:
    - Топ 25%: звезды (ROI > 75й перцентиль)
    - 25-50%: перформеры (ROI между медианой и 75й перцентиль)
    - 50-75%: середнячки (ROI между 25й перцентиль и медианой)
    - Нижние 25%: аутсайдеры (ROI < 25й перцентиль)
    - Минимальный расход > min_daily_spend (по умолчанию $1/день)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="performance_segmenter",
            name="Сегменты эффективности",
            category="segmentation",
            description="Разделение кампаний на топ/средние/слабые",
            detailed_description="Сегментирует все кампании по эффективности для применения разных стратегий управления. Автоматическое распределение по квартилям ROI.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["segmentation", "performance", "roi", "quartiles"]
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
                "min_daily_spend": 1.0,  # минимальный средний расход в день ($)
                "min_clicks": 50  # минимум кликов за период
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
            "min_daily_spend": {
                "label": "Минимальный расход в день ($)",
                "description": "Минимальный средний расход для включения в сегментацию",
                "type": "number",
                "min": 0.5,
                "max": 10000,
                "default": 1.0
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов за период для включения в анализ",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 50
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ и сегментация кампаний по эффективности.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о сегментах кампаний
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_daily_spend = config.params.get("min_daily_spend", 1.0)
        min_clicks = config.params.get("min_clicks", 50)

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
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
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
                "total_clicks": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                campaigns_data[campaign_id]["total_clicks"] += row.clicks or 0
                campaigns_data[campaign_id]["total_cost"] += float(row.cost) if row.cost else 0
                campaigns_data[campaign_id]["total_revenue"] += float(row.revenue) if row.revenue else 0
                campaigns_data[campaign_id]["total_leads"] += row.leads or 0

            # Подготовка кампаний для сегментации
            campaigns = []
            all_rois = []

            for campaign_id, data in campaigns_data.items():
                avg_daily_spend = data["total_cost"] / days

                # Фильтры
                if avg_daily_spend < min_daily_spend:
                    continue
                if data["total_clicks"] < min_clicks:
                    continue
                if data["total_cost"] == 0:
                    continue

                # Расчет метрик
                roi = ((data["total_revenue"] - data["total_cost"]) / data["total_cost"] * 100) if data["total_cost"] > 0 else -100
                cr = (data["total_leads"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0
                profit = data["total_revenue"] - data["total_cost"]

                campaign_info = {
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_clicks": data["total_clicks"],
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "total_leads": data["total_leads"],
                    "profit": round(profit, 2),
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "roi": round(roi, 1),
                    "cr": round(cr, 2)
                }

                campaigns.append(campaign_info)
                all_rois.append(roi)

            if not campaigns:
                return {
                    "segments": [],
                    "summary": {
                        "total_campaigns": 0,
                        "stars_count": 0,
                        "performers_count": 0,
                        "average_count": 0,
                        "underperformers_count": 0
                    },
                    "quartiles": {},
                    "period": {
                        "days": days,
                        "date_from": date_from.isoformat(),
                        "date_to": datetime.now().date().isoformat()
                    },
                    "params": {
                        "min_daily_spend": min_daily_spend,
                        "min_clicks": min_clicks
                    }
                }

            # Вычисление перцентилей (квартилей)
            sorted_rois = sorted(all_rois)
            q1 = statistics.quantiles(sorted_rois, n=4)[0]  # 25й перцентиль
            q2 = statistics.quantiles(sorted_rois, n=4)[1]  # 50й перцентиль (медиана)
            q3 = statistics.quantiles(sorted_rois, n=4)[2]  # 75й перцентиль

            # Сегментация кампаний
            segments = {
                "stars": [],          # Топ 25% (ROI >= Q3)
                "performers": [],     # 25-50% (Q2 <= ROI < Q3)
                "average": [],        # 50-75% (Q1 <= ROI < Q2)
                "underperformers": [] # Нижние 25% (ROI < Q1)
            }

            for campaign in campaigns:
                roi = campaign["roi"]

                if roi >= q3:
                    segments["stars"].append(campaign)
                elif roi >= q2:
                    segments["performers"].append(campaign)
                elif roi >= q1:
                    segments["average"].append(campaign)
                else:
                    segments["underperformers"].append(campaign)

            # Сортировка сегментов по ROI (убывание)
            for segment_name in segments:
                segments[segment_name].sort(key=lambda x: x["roi"], reverse=True)

            # Создание структурированного вывода
            segments_output = [
                {
                    "segment_name": "Звезды (топ 25%)",
                    "segment_id": "stars",
                    "description": f"ROI > {q3:.1f}%",
                    "campaign_count": len(segments["stars"]),
                    "total_cost": round(sum(c["total_cost"] for c in segments["stars"]), 2),
                    "total_revenue": round(sum(c["total_revenue"] for c in segments["stars"]), 2),
                    "total_profit": round(sum(c["profit"] for c in segments["stars"]), 2),
                    "avg_roi": round(sum(c["roi"] for c in segments["stars"]) / len(segments["stars"]), 1) if segments["stars"] else 0,
                    "campaigns": segments["stars"]
                },
                {
                    "segment_name": "Перформеры (25-50%)",
                    "segment_id": "performers",
                    "description": f"{q2:.1f}% < ROI <= {q3:.1f}%",
                    "campaign_count": len(segments["performers"]),
                    "total_cost": round(sum(c["total_cost"] for c in segments["performers"]), 2),
                    "total_revenue": round(sum(c["total_revenue"] for c in segments["performers"]), 2),
                    "total_profit": round(sum(c["profit"] for c in segments["performers"]), 2),
                    "avg_roi": round(sum(c["roi"] for c in segments["performers"]) / len(segments["performers"]), 1) if segments["performers"] else 0,
                    "campaigns": segments["performers"]
                },
                {
                    "segment_name": "Середнячки (50-75%)",
                    "segment_id": "average",
                    "description": f"{q1:.1f}% < ROI <= {q2:.1f}%",
                    "campaign_count": len(segments["average"]),
                    "total_cost": round(sum(c["total_cost"] for c in segments["average"]), 2),
                    "total_revenue": round(sum(c["total_revenue"] for c in segments["average"]), 2),
                    "total_profit": round(sum(c["profit"] for c in segments["average"]), 2),
                    "avg_roi": round(sum(c["roi"] for c in segments["average"]) / len(segments["average"]), 1) if segments["average"] else 0,
                    "campaigns": segments["average"]
                },
                {
                    "segment_name": "Аутсайдеры (нижние 25%)",
                    "segment_id": "underperformers",
                    "description": f"ROI <= {q1:.1f}%",
                    "campaign_count": len(segments["underperformers"]),
                    "total_cost": round(sum(c["total_cost"] for c in segments["underperformers"]), 2),
                    "total_revenue": round(sum(c["total_revenue"] for c in segments["underperformers"]), 2),
                    "total_profit": round(sum(c["profit"] for c in segments["underperformers"]), 2),
                    "avg_roi": round(sum(c["roi"] for c in segments["underperformers"]) / len(segments["underperformers"]), 1) if segments["underperformers"] else 0,
                    "campaigns": segments["underperformers"]
                }
            ]

            return {
                "segments": segments_output,
                "summary": {
                    "total_campaigns": len(campaigns),
                    "stars_count": len(segments["stars"]),
                    "performers_count": len(segments["performers"]),
                    "average_count": len(segments["average"]),
                    "underperformers_count": len(segments["underperformers"])
                },
                "quartiles": {
                    "q1": round(q1, 1),
                    "q2": round(q2, 1),
                    "q3": round(q3, 1)
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_daily_spend": min_daily_spend,
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
        segments = raw_data.get("segments", [])
        summary = raw_data.get("summary", {})

        if not segments:
            return []

        charts = []

        # График распределения кампаний по сегментам
        charts.append({
            "id": "segmenter_distribution",
            "type": "pie",
            "data": {
                "labels": [s["segment_name"] for s in segments],
                "datasets": [{
                    "data": [s["campaign_count"] for s in segments],
                    "backgroundColor": [
                        "rgba(75, 192, 192, 0.8)",   # Звезды - зеленый
                        "rgba(54, 162, 235, 0.8)",   # Перформеры - синий
                        "rgba(255, 206, 86, 0.8)",   # Середнячки - желтый
                        "rgba(255, 99, 132, 0.8)"    # Аутсайдеры - красный
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение кампаний по сегментам"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График прибыли по сегментам
        charts.append({
            "id": "segmenter_profit",
            "type": "bar",
            "data": {
                "labels": [s["segment_name"] for s in segments],
                "datasets": [{
                    "label": "Прибыль ($)",
                    "data": [s["total_profit"] for s in segments],
                    "backgroundColor": [
                        "rgba(75, 192, 192, 0.6)" if p >= 0 else "rgba(255, 99, 132, 0.6)"
                        for p in [s["total_profit"] for s in segments]
                    ],
                    "borderColor": [
                        "rgba(75, 192, 192, 1)" if p >= 0 else "rgba(255, 99, 132, 1)"
                        for p in [s["total_profit"] for s in segments]
                    ],
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Прибыль по сегментам"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Прибыль ($)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для сегментации кампаний.
        """
        segments = raw_data.get("segments", [])
        alerts = []

        # Находим аутсайдеров (нижний сегмент)
        underperformers = next((s for s in segments if s["segment_id"] == "underperformers"), None)
        if underperformers and underperformers["campaign_count"] > 0:
            total_loss = abs(underperformers["total_profit"]) if underperformers["total_profit"] < 0 else 0

            if total_loss > 0:
                message = f"Обнаружено {underperformers['campaign_count']} кампаний в сегменте Аутсайдеров\n\n"
                message += f"Общий убыток сегмента: ${total_loss:.2f}\n"
                message += f"Средний ROI: {underperformers['avg_roi']:.1f}%\n\n"
                message += "Топ-3 худших кампании:\n"

                for i, campaign in enumerate(underperformers["campaigns"][:3], 1):
                    message += f"{i}. {campaign['name']}: ROI {campaign['roi']:.1f}%, убыток ${abs(campaign['profit']):.2f}\n"

                alerts.append({
                    "type": "segmenter_underperformers",
                    "severity": "high",
                    "message": message,
                    "recommended_action": "Рассмотрите возможность остановки или оптимизации этих кампаний",
                    "campaigns_count": underperformers["campaign_count"],
                    "total_loss": round(total_loss, 2)
                })

        return alerts
