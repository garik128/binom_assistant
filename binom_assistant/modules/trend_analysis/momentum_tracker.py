"""
Модуль анализа силы импульса (momentum)
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


class MomentumTracker(BaseModule):
    """
    Трекер силы импульса (momentum).

    Определяет ускорение или замедление роста метрик сравнивая недельные периоды:
    - Текущая неделя vs предыдущая неделя
    - Расчет коэффициента ускорения
    - Учет объемов для взвешивания
    - Индекс momentum от -100 до +100

    Помогает понять набирает ли кампания обороты или теряет импульс.
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="momentum_tracker",
            name="Сила импульса",
            category="trend_analysis",
            description="Сравнивает динамику текущей и предыдущей недели для определения ускорения/замедления роста",
            detailed_description=(
                "Модуль анализирует изменение скорости роста метрик между двумя недельными периодами. "
                "Вычисляет индекс momentum от -100 до +100, показывающий ускоряется ли рост кампании "
                "или происходит замедление. Учитывает объемы трафика для более точной оценки."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["momentum", "acceleration", "roi", "trend", "weekly"]
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
                "current_week_days": 7,  # Текущая неделя (сегодня включительно)
                "previous_week_days": 7,  # Предыдущая неделя
                "min_spend_per_week": 5,  # Минимум $5 трат за неделю
                "min_clicks_per_week": 30,  # Минимум 30 кликов за неделю
                "severity_high": 30,  # weighted_momentum для high severity (положительный - ускорение)
                "severity_medium": 15,  # weighted_momentum для medium severity (положительный - ускорение)
                "severity_high_negative": -30,  # weighted_momentum для high severity (отрицательный - замедление)
                "severity_medium_negative": -15,  # weighted_momentum для medium severity (отрицательный - замедление)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.

        Returns:
            Dict с описаниями параметров
        """
        return {
            "current_week_days": {
                "label": "Дней текущей недели",
                "description": "Количество дней для анализа текущей недели (включая сегодня)",
                "type": "number",
                "min": 1,
                "max": 365,
                "step": 1
            },
            "previous_week_days": {
                "label": "Дней предыдущей недели",
                "description": "Количество дней для анализа предыдущей недели",
                "type": "number",
                "min": 1,
                "max": 365,
                "step": 1
            },
            "min_spend_per_week": {
                "label": "Минимальный расход за неделю",
                "description": "Минимальный расход для включения кампании в анализ ($)",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 1
            },
            "min_clicks_per_week": {
                "label": "Минимум кликов за неделю",
                "description": "Минимальное количество кликов для включения в анализ",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 10
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "momentum_index",
            "metric_label": "Индекс momentum",
            "metric_unit": "",
            "description": "Пороги критичности на основе силы импульса (положительные значения - ускорение, отрицательные - замедление)",
            "thresholds": {
                "severity_high": {
                    "label": "Высокий импульс (ускорение)",
                    "description": "Momentum выше этого значения считается высоким ускорением",
                    "type": "number",
                    "min": 10,
                    "max": 100,
                    "step": 5,
                    "default": 30
                },
                "severity_medium": {
                    "label": "Средний импульс (ускорение)",
                    "description": "Momentum выше этого значения (но ниже высокого) считается средним ускорением",
                    "type": "number",
                    "min": 5,
                    "max": 50,
                    "step": 5,
                    "default": 15
                },
                "severity_high_negative": {
                    "label": "Высокое замедление",
                    "description": "Momentum ниже этого значения считается высоким замедлением",
                    "type": "number",
                    "min": -100,
                    "max": -10,
                    "step": 5,
                    "default": -30
                },
                "severity_medium_negative": {
                    "label": "Среднее замедление",
                    "description": "Momentum ниже этого значения (но выше высокого замедления) считается средним замедлением",
                    "type": "number",
                    "min": -50,
                    "max": -5,
                    "step": 5,
                    "default": -15
                }
            },
            "levels": [
                {"value": "high", "label": "Высокое ускорение", "color": "#10b981", "condition": "momentum >= high"},
                {"value": "medium", "label": "Среднее ускорение", "color": "#3b82f6", "condition": "medium <= momentum < high"},
                {"value": "low", "label": "Стабильно", "color": "#6b7280", "condition": "medium_negative < momentum < medium"},
                {"value": "medium", "label": "Среднее замедление", "color": "#f59e0b", "condition": "high_negative < momentum <= medium_negative"},
                {"value": "high", "label": "Высокое замедление", "color": "#ef4444", "condition": "momentum <= high_negative"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ силы импульса через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о momentum кампаний
        """
        # Получение параметров
        current_week_days = config.params.get("current_week_days", 7)
        previous_week_days = config.params.get("previous_week_days", 7)
        min_spend_per_week = config.params.get("min_spend_per_week", 5)
        min_clicks_per_week = config.params.get("min_clicks_per_week", 30)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", 30)
        severity_medium_threshold = config.params.get("severity_medium", 15)
        severity_high_negative_threshold = config.params.get("severity_high_negative", -30)
        severity_medium_negative_threshold = config.params.get("severity_medium_negative", -15)

        # Валидация периодов
        if current_week_days < 7 or current_week_days > 7:
            current_week_days = 7
        if previous_week_days < 7 or previous_week_days > 7:
            previous_week_days = 7

        # Расчет дат
        today = datetime.now().date()
        current_week_start = today - timedelta(days=current_week_days - 1)
        previous_week_start = current_week_start - timedelta(days=previous_week_days)
        previous_week_end = current_week_start - timedelta(days=1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем статистику для обоих периодов
            query = session.query(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date,
                func.sum(CampaignStatsDaily.cost).label('cost'),
                func.sum(CampaignStatsDaily.revenue).label('revenue'),
                func.sum(CampaignStatsDaily.clicks).label('clicks'),
                func.sum(CampaignStatsDaily.leads).label('leads')
            ).filter(
                CampaignStatsDaily.date >= previous_week_start,
                CampaignStatsDaily.date <= today,
                CampaignStatsDaily.cost > 0
            ).group_by(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date
            ).order_by(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date
            )

            stats_by_date = query.all()

            # Группируем данные по кампаниям и периодам
            campaigns_data = {}
            for row in stats_by_date:
                campaign_id = row.campaign_id
                if campaign_id not in campaigns_data:
                    campaigns_data[campaign_id] = {
                        'current_week': [],
                        'previous_week': []
                    }

                # Определяем к какому периоду относится запись
                if current_week_start <= row.date <= today:
                    period = 'current_week'
                elif previous_week_start <= row.date <= previous_week_end:
                    period = 'previous_week'
                else:
                    continue

                campaigns_data[campaign_id][period].append({
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

            # Анализируем momentum
            accelerating = []  # Набирающие обороты
            decelerating = []  # Теряющие импульс
            stable = []  # Стабильные

            for campaign_id, periods_data in campaigns_data.items():
                current_data = periods_data['current_week']
                previous_data = periods_data['previous_week']

                # Пропускаем если недостаточно данных
                if not current_data or not previous_data:
                    continue

                # Агрегируем статистику по периодам
                # Текущая неделя
                current_cost = sum(d['cost'] for d in current_data)
                current_revenue = sum(d['revenue'] for d in current_data)
                current_clicks = sum(d['clicks'] for d in current_data)
                current_leads = sum(d['leads'] for d in current_data)

                # Предыдущая неделя
                previous_cost = sum(d['cost'] for d in previous_data)
                previous_revenue = sum(d['revenue'] for d in previous_data)
                previous_clicks = sum(d['clicks'] for d in previous_data)
                previous_leads = sum(d['leads'] for d in previous_data)

                # Фильтрация по минимальным порогам
                if current_cost < min_spend_per_week or previous_cost < min_spend_per_week:
                    continue
                if current_clicks < min_clicks_per_week or previous_clicks < min_clicks_per_week:
                    continue

                # Вычисляем метрики для обоих периодов
                # ROI
                current_roi = ((current_revenue - current_cost) / current_cost * 100) if current_cost > 0 else 0
                previous_roi = ((previous_revenue - previous_cost) / previous_cost * 100) if previous_cost > 0 else 0

                # EPC (прибыль на клик)
                current_epc = (current_revenue / current_clicks) if current_clicks > 0 else 0
                previous_epc = (previous_revenue / previous_clicks) if previous_clicks > 0 else 0

                # CR (конверсия)
                current_cr = (current_leads / current_clicks * 100) if current_clicks > 0 else 0
                previous_cr = (previous_leads / previous_clicks * 100) if previous_clicks > 0 else 0

                # Вычисляем изменения (дельта)
                roi_delta_current = current_roi - previous_roi
                epc_delta_current = current_epc - previous_epc
                cr_delta_current = current_cr - previous_cr

                # Для предыдущей недели нам нужно сравнить с неделей до нее
                # Но у нас нет данных за 3 недели назад
                # Поэтому используем упрощенный подход:
                # momentum = изменение скорости изменения ROI

                # Простой подход: momentum = изменение ROI между неделями
                # Положительное значение = ускорение, отрицательное = замедление

                # Рассчитываем индекс momentum (-100 до +100)
                # Основа: изменение ROI
                momentum_roi = roi_delta_current

                # Учитываем объемы (больший вес для кампаний с большим трафиком)
                volume_weight = min(current_clicks / 1000, 1.0)  # Нормализация 0-1

                # Финальный индекс momentum
                # Ограничиваем от -100 до +100
                momentum_index = max(-100, min(100, momentum_roi))

                # Weighted momentum с учетом объема
                weighted_momentum = momentum_index * (0.7 + 0.3 * volume_weight)

                # Определяем категорию на основе настраиваемых порогов
                if weighted_momentum > severity_medium_threshold:
                    category = "accelerating"
                    severity = "high" if weighted_momentum > severity_high_threshold else "medium"
                elif weighted_momentum < severity_medium_negative_threshold:
                    category = "decelerating"
                    severity = "high" if weighted_momentum < severity_high_negative_threshold else "medium"
                else:
                    category = "stable"
                    severity = "low"

                # Формируем данные
                campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы"
                })

                campaign_momentum = {
                    "campaign_id": campaign_id,
                    "binom_id": campaign_info['binom_id'],
                    "name": campaign_info['name'],
                    "group": campaign_info['group'],

                    # Текущая неделя
                    "current_cost": round(current_cost, 2),
                    "current_revenue": round(current_revenue, 2),
                    "current_roi": round(current_roi, 2),
                    "current_clicks": current_clicks,
                    "current_leads": current_leads,
                    "current_cr": round(current_cr, 2),
                    "current_epc": round(current_epc, 2),

                    # Предыдущая неделя
                    "previous_cost": round(previous_cost, 2),
                    "previous_revenue": round(previous_revenue, 2),
                    "previous_roi": round(previous_roi, 2),
                    "previous_clicks": previous_clicks,
                    "previous_leads": previous_leads,
                    "previous_cr": round(previous_cr, 2),
                    "previous_epc": round(previous_epc, 2),

                    # Изменения
                    "roi_change": round(roi_delta_current, 2),
                    "epc_change": round(epc_delta_current, 2),
                    "cr_change": round(cr_delta_current, 2),

                    # Momentum
                    "momentum_index": round(weighted_momentum, 2),
                    "category": category,
                    "severity": severity,

                    # Обязательные поля для таблицы
                    "total_cost": round(current_cost + previous_cost, 2),
                    "total_revenue": round(current_revenue + previous_revenue, 2),
                    "avg_roi": round((current_roi + previous_roi) / 2, 2)
                }

                # Распределяем по категориям
                if category == "accelerating":
                    accelerating.append(campaign_momentum)
                elif category == "decelerating":
                    decelerating.append(campaign_momentum)
                else:
                    stable.append(campaign_momentum)

            # Сортировка
            accelerating.sort(key=lambda x: x['momentum_index'], reverse=True)
            decelerating.sort(key=lambda x: x['momentum_index'])
            stable.sort(key=lambda x: x['current_roi'], reverse=True)

            # Объединяем для общей таблицы
            all_campaigns = accelerating + stable + decelerating

            return {
                "campaigns": all_campaigns,
                "accelerating": accelerating,
                "decelerating": decelerating,
                "stable": stable,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_accelerating": len(accelerating),
                    "total_decelerating": len(decelerating),
                    "total_stable": len(stable),
                    "avg_momentum_index": round(
                        sum(c['momentum_index'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "strongest_acceleration": round(accelerating[0]['momentum_index'], 2) if accelerating else 0,
                    "strongest_deceleration": round(decelerating[0]['momentum_index'], 2) if decelerating else 0
                },
                "period": {
                    "current_week_start": current_week_start.isoformat(),
                    "current_week_end": today.isoformat(),
                    "previous_week_start": previous_week_start.isoformat(),
                    "previous_week_end": previous_week_end.isoformat()
                },
                "thresholds": {
                    "min_spend_per_week": min_spend_per_week,
                    "min_clicks_per_week": min_clicks_per_week,
                    "severity_high": severity_high_threshold,
                    "severity_medium": severity_medium_threshold,
                    "severity_high_negative": severity_high_negative_threshold,
                    "severity_medium_negative": severity_medium_negative_threshold
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
        accelerating = raw_data["accelerating"][:10]
        decelerating = raw_data["decelerating"][:10]

        charts = []

        # График: Ускоряющиеся кампании
        if accelerating:
            charts.append({
                "id": "accelerating_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in accelerating],
                    "datasets": [{
                        "label": "Индекс momentum",
                        "data": [c["momentum_index"] for c in accelerating],
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
                            "text": "Топ-10 ускоряющихся кампаний"
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

        # График: Замедляющиеся кампании
        if decelerating:
            charts.append({
                "id": "decelerating_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in decelerating],
                    "datasets": [{
                        "label": "Индекс momentum",
                        "data": [c["momentum_index"] for c in decelerating],
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
                            "text": "Топ-10 замедляющихся кампаний"
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

        # Doughnut: Распределение по категориям
        summary = raw_data["summary"]
        if summary["total_analyzed"] > 0:
            charts.append({
                "id": "momentum_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Ускоряются", "Стабильные", "Замедляются"],
                    "datasets": [{
                        "data": [
                            summary["total_accelerating"],
                            summary["total_stable"],
                            summary["total_decelerating"]
                        ],
                        "backgroundColor": [
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(107, 114, 128, 0.8)",
                            "rgba(239, 68, 68, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по momentum"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для значимых изменений momentum.
        """
        alerts = []
        summary = raw_data["summary"]
        accelerating = raw_data["accelerating"]
        decelerating = raw_data["decelerating"]
        thresholds = raw_data.get("thresholds", {})

        # Получаем пороги для сообщений
        severity_high_threshold = thresholds.get("severity_high", 30)
        severity_high_negative_threshold = thresholds.get("severity_high_negative", -30)

        # Алерт о сильно ускоряющихся кампаниях
        strong_acceleration = [c for c in accelerating if c['momentum_index'] > severity_high_threshold]
        if strong_acceleration:
            top_3 = strong_acceleration[:3]
            message = f"Обнаружено {len(strong_acceleration)} кампаний с сильным ускорением роста (momentum > {severity_high_threshold})"
            message += "\n\nТоп-3 ускоряющихся:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: momentum {camp['momentum_index']:+.1f}, ROI {camp['current_roi']:.1f}% ({camp['roi_change']:+.1f}%)"

            alerts.append({
                "type": "strong_acceleration",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите увеличение бюджета для кампаний с сильным положительным momentum",
                "campaigns_count": len(strong_acceleration)
            })

        # Алерт о сильно замедляющихся кампаниях
        strong_deceleration = [c for c in decelerating if c['momentum_index'] < severity_high_negative_threshold]
        if strong_deceleration:
            top_3 = strong_deceleration[:3]
            message = f"ВНИМАНИЕ: {len(strong_deceleration)} кампаний с сильным замедлением (momentum < {severity_high_negative_threshold})"
            message += "\n\nТоп-3 замедляющихся:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: momentum {camp['momentum_index']:+.1f}, ROI {camp['current_roi']:.1f}% ({camp['roi_change']:+.1f}%)"

            alerts.append({
                "type": "strong_deceleration",
                "severity": "high",
                "message": message,
                "recommended_action": "Срочно проверьте причины потери импульса и оптимизируйте кампании",
                "campaigns_count": len(strong_deceleration)
            })

        # Алерт об общем negative momentum
        if summary["avg_momentum_index"] < -10:
            message = f"Средний momentum портфеля отрицательный: {summary['avg_momentum_index']:.1f}"
            message += f"\nЗамедляющихся кампаний: {summary['total_decelerating']}"
            message += f"\nУскоряющихся кампаний: {summary['total_accelerating']}"

            alerts.append({
                "type": "negative_portfolio_momentum",
                "severity": "high",
                "message": message,
                "recommended_action": "Общий негативный тренд портфеля - требуется срочная оптимизация",
                "campaigns_count": summary["total_analyzed"]
            })

        return alerts
