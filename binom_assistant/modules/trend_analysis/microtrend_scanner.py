"""
Модуль анализа микро-трендов (3-7 дней)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager

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


class MicrotrendScanner(BaseModule):
    """
    Сканер микро-трендов.

    Анализирует краткосрочные тренды (3-7 дней) в метриках кампаний:
    - ROI (рентабельность)
    - CTR (кликабельность)
    - CR (конверсия)
    - EPC (прибыль на клик)

    Выявляет:
    - Растущие тренды (положительные изменения)
    - Падающие тренды (отрицательные изменения)
    - Скорость изменения метрик
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="microtrend_scanner",
            name="Сканер микро-трендов",
            category="trend_analysis",
            description="Анализирует краткосрочные тренды (3-7 дней) в ключевых метриках кампаний",
            detailed_description=(
                "Модуль отслеживает динамику изменения метрик кампаний за короткие периоды (3-7 дней). "
                "Выявляет растущие и падающие тренды по ROI, CTR, CR и EPC. "
                "Помогает быстро реагировать на краткосрочные изменения в производительности кампаний."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["trends", "roi", "ctr", "conversion", "short-term"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Некритический модуль - не запускать автоматически
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=45,
            cache_ttl_seconds=3600,
            params={
                "days": 7,  # период анализа (3-7 дней)
                "min_spend": 3,  # минимум $3 трат за период
                "min_clicks": 50,  # минимум 50 кликов за период
                "significant_change": 15,  # значимое изменение метрики (в %)
            }
        )

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ микро-трендов через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о микро-трендах
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_spend = config.params.get("min_spend", 3)
        min_clicks = config.params.get("min_clicks", 50)
        significant_change = config.params.get("significant_change", 15)

        # Валидация периода
        if days < 3 or days > 7:
            days = 7

        date_from = datetime.now().date() - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем дневную статистику по кампаниям
            query = session.query(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date,
                func.sum(CampaignStatsDaily.cost).label('cost'),
                func.sum(CampaignStatsDaily.revenue).label('revenue'),
                func.sum(CampaignStatsDaily.clicks).label('clicks'),
                func.sum(CampaignStatsDaily.leads).label('leads')
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost > 0
            ).group_by(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date
            ).order_by(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date
            )

            stats_by_date = query.all()

            # Группируем данные по кампаниям
            campaigns_data = {}
            for row in stats_by_date:
                campaign_id = row.campaign_id
                if campaign_id not in campaigns_data:
                    campaigns_data[campaign_id] = []

                campaigns_data[campaign_id].append({
                    'date': row.date,
                    'cost': float(row.cost),
                    'revenue': float(row.revenue),
                    'clicks': int(row.clicks),
                    'leads': int(row.leads)
                })

            # Загружаем информацию о кампаниях
            campaign_ids = list(campaigns_data.keys())
            campaigns_info = {}
            if campaign_ids:
                campaigns_query = session.query(Campaign).filter(
                    Campaign.internal_id.in_(campaign_ids)
                )
                for campaign in campaigns_query.all():
                    campaigns_info[campaign.internal_id] = {
                        'binom_id': campaign.binom_id,
                        'name': campaign.current_name,
                        'group': campaign.group_name or "Без группы"
                    }

            # Анализируем тренды
            positive_trends = []
            negative_trends = []
            neutral_campaigns = 0

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < 3:
                    continue

                # Агрегированная статистика
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)

                # Фильтрация по минимальным порогам
                if total_cost < min_spend or total_clicks < min_clicks:
                    continue

                # ИСПРАВЛЕНО: Используем линейную регрессию для определения тренда
                # Вместо сравнения половин, анализируем направление изменения метрик во времени

                # Вычисляем дневные ROI, EPC и CR
                daily_metrics = []
                for i, d in enumerate(daily_data):
                    roi = ((d['revenue'] - d['cost']) / d['cost'] * 100) if d['cost'] > 0 else 0
                    epc = (d['revenue'] / d['clicks']) if d['clicks'] > 0 else 0
                    cr = (d['leads'] / d['clicks'] * 100) if d['clicks'] > 0 else 0
                    daily_metrics.append({
                        'day': i,
                        'roi': roi,
                        'epc': epc,
                        'cr': cr
                    })

                # Простая линейная регрессия: slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
                n = len(daily_metrics)

                # ROI тренд
                sum_x = sum(m['day'] for m in daily_metrics)
                sum_y_roi = sum(m['roi'] for m in daily_metrics)
                sum_xy_roi = sum(m['day'] * m['roi'] for m in daily_metrics)
                sum_x2 = sum(m['day'] ** 2 for m in daily_metrics)

                roi_slope = ((n * sum_xy_roi - sum_x * sum_y_roi) /
                            (n * sum_x2 - sum_x ** 2)) if (n * sum_x2 - sum_x ** 2) != 0 else 0

                # EPC тренд
                sum_y_epc = sum(m['epc'] for m in daily_metrics)
                sum_xy_epc = sum(m['day'] * m['epc'] for m in daily_metrics)
                epc_slope = ((n * sum_xy_epc - sum_x * sum_y_epc) /
                            (n * sum_x2 - sum_x ** 2)) if (n * sum_x2 - sum_x ** 2) != 0 else 0

                # CR тренд
                sum_y_cr = sum(m['cr'] for m in daily_metrics)
                sum_xy_cr = sum(m['day'] * m['cr'] for m in daily_metrics)
                cr_slope = ((n * sum_xy_cr - sum_x * sum_y_cr) /
                           (n * sum_x2 - sum_x ** 2)) if (n * sum_x2 - sum_x ** 2) != 0 else 0

                # Изменение за весь период (slope * количество дней)
                roi_change = roi_slope * (n - 1)

                # Процентное изменение EPC
                avg_epc = sum_y_epc / n if n > 0 else 0
                epc_change = (epc_slope * (n - 1) / avg_epc * 100) if avg_epc > 0 else 0

                # Изменение CR
                cr_change = cr_slope * (n - 1)

                # Общий ROI
                total_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
                total_epc = (total_revenue / total_clicks) if total_clicks > 0 else 0
                total_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0

                # Определяем тренд
                trend_direction = "neutral"
                trend_strength = 0

                # Основной индикатор - изменение ROI
                if abs(roi_change) >= significant_change:
                    trend_strength = abs(roi_change)
                    if roi_change > 0:
                        trend_direction = "growing"
                    else:
                        trend_direction = "falling"
                else:
                    neutral_campaigns += 1
                    continue

                # Формируем данные о тренде
                campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы"
                })

                trend_data = {
                    "campaign_id": campaign_id,
                    "binom_id": campaign_info['binom_id'],
                    "name": campaign_info['name'],
                    "group": campaign_info['group'],
                    "total_cost": total_cost,
                    "total_revenue": total_revenue,
                    "total_clicks": total_clicks,
                    "total_leads": total_leads,
                    "current_roi": round(total_roi, 2),
                    "roi_change": round(roi_change, 2),
                    "epc": round(total_epc, 2),
                    "epc_change": round(epc_change, 2),
                    "cr": round(total_cr, 2),
                    "cr_change": round(cr_change, 2),
                    "trend_strength": round(trend_strength, 2),
                    "days_analyzed": len(daily_data)
                }

                if trend_direction == "growing":
                    positive_trends.append(trend_data)
                else:
                    negative_trends.append(trend_data)

            # Сортировка: положительные - по убыванию ROI change, отрицательные - по возрастанию
            positive_trends.sort(key=lambda x: x['roi_change'], reverse=True)
            negative_trends.sort(key=lambda x: x['roi_change'])

            return {
                "positive_trends": positive_trends,
                "negative_trends": negative_trends,
                "summary": {
                    "total_positive": len(positive_trends),
                    "total_negative": len(negative_trends),
                    "total_neutral": neutral_campaigns,
                    "avg_roi_change_positive": round(
                        sum(t['roi_change'] for t in positive_trends) / len(positive_trends), 2
                    ) if positive_trends else 0,
                    "avg_roi_change_negative": round(
                        sum(t['roi_change'] for t in negative_trends) / len(negative_trends), 2
                    ) if negative_trends else 0
                },
                "period_days": days,
                "thresholds": {
                    "min_spend": min_spend,
                    "min_clicks": min_clicks,
                    "significant_change": significant_change
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        Вся информация теперь в алертах.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        positive = raw_data["positive_trends"][:10]
        negative = raw_data["negative_trends"][:10]

        charts = []

        # График положительных трендов
        if positive:
            charts.append({
                "id": "positive_trends_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in positive],
                    "datasets": [{
                        "label": "Изменение ROI (%)",
                        "data": [c["roi_change"] for c in positive],
                        "backgroundColor": "rgba(16, 185, 129, 0.5)",
                        "borderColor": "rgba(16, 185, 129, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-10 растущих трендов"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True
                        }
                    }
                }
            })

        # График отрицательных трендов
        if negative:
            charts.append({
                "id": "negative_trends_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in negative],
                    "datasets": [{
                        "label": "Изменение ROI (%)",
                        "data": [c["roi_change"] for c in negative],
                        "backgroundColor": "rgba(239, 68, 68, 0.5)",
                        "borderColor": "rgba(239, 68, 68, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-10 падающих трендов"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": False
                        }
                    }
                }
            })

        # Pie chart: распределение трендов
        summary = raw_data["summary"]
        if summary["total_positive"] > 0 or summary["total_negative"] > 0:
            charts.append({
                "id": "trends_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Растущие", "Падающие", "Стабильные"],
                    "datasets": [{
                        "data": [
                            summary["total_positive"],
                            summary["total_negative"],
                            summary["total_neutral"]
                        ],
                        "backgroundColor": [
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(239, 68, 68, 0.8)",
                            "rgba(107, 114, 128, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение трендов"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для значимых трендов.
        """
        alerts = []
        summary = raw_data["summary"]
        positive = raw_data["positive_trends"]
        negative = raw_data["negative_trends"]

        # Алерт о сильных положительных трендах
        strong_positive = [t for t in positive if t['roi_change'] >= 30]
        if strong_positive:
            top_3 = strong_positive[:3]
            message = f"Обнаружено {len(strong_positive)} кампаний с сильным ростом ROI (>30%)"
            message += "\n\nТоп-3 растущих:"
            for i, trend in enumerate(top_3, 1):
                message += f"\n{i}. {trend['name']}: ROI {trend['roi_change']:+.1f}% (текущий {trend['current_roi']:.1f}%)"

            alerts.append({
                "type": "strong_positive_trends",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите увеличение бюджета для растущих кампаний",
                "campaigns_count": len(strong_positive)
            })

        # Алерт о сильных отрицательных трендах
        strong_negative = [t for t in negative if t['roi_change'] <= -30]
        if strong_negative:
            top_3 = strong_negative[:3]
            message = f"ВНИМАНИЕ: {len(strong_negative)} кампаний с резким падением ROI (>30%)"
            message += "\n\nТоп-3 падающих:"
            for i, trend in enumerate(top_3, 1):
                message += f"\n{i}. {trend['name']}: ROI {trend['roi_change']:+.1f}% (текущий {trend['current_roi']:.1f}%)"

            alerts.append({
                "type": "strong_negative_trends",
                "severity": "high",
                "message": message,
                "recommended_action": "Срочно проанализируйте причины падения и примите меры",
                "campaigns_count": len(strong_negative)
            })

        return alerts
