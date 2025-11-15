"""
Модуль анализа ускорения динамики
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


class AccelerationMonitor(BaseModule):
    """
    Монитор ускорения динамики (acceleration).

    Определяет изменение скорости роста метрик (вторая производная):
    - Расчет первой производной (скорость изменения)
    - Расчет второй производной (ускорение)
    - Сглаживание шума moving average 3 дня
    - Классификация: ускоряется/стабильно/замедляется

    Показывает не просто рост, а его ускорение или торможение.
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="acceleration_monitor",
            name="Ускорение динамики",
            category="trend_analysis",
            description="Измеряет ускорение или замедление роста метрик через вторую производную",
            detailed_description=(
                "Модуль анализирует изменение скорости роста метрик (вторая производная). "
                "Использует скользящее среднее для сглаживания шума и классифицирует кампании "
                "на ускоряющиеся, стабильные и замедляющиеся. Помогает определить не просто рост, "
                "а его динамику: растет ли рост или наоборот тормозит."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["acceleration", "derivative", "velocity", "roi", "trend"]
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
                "days": 7,  # Период анализа (сегодня включительно)
                "min_spend": 1,  # Минимум $1 трат в день
                "min_clicks": 20,  # Минимум 20 кликов за период
                "smoothing_window": 3,  # Окно сглаживания (дней)
                "severity_high": 5,  # current_acceleration для high severity (положительное - ускорение)
                "severity_medium": 2,  # current_acceleration для medium severity (положительное - ускорение)
                "severity_high_negative": -5,  # current_acceleration для high severity (отрицательное - замедление)
                "severity_medium_negative": -2,  # current_acceleration для medium severity (отрицательное - замедление)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.

        Returns:
            Dict с описаниями параметров
        """
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа динамики (включая сегодня)",
                "type": "number",
                "min": 5,
                "max": 365,
                "step": 1
            },
            "min_spend": {
                "label": "Минимальный расход в день",
                "description": "Минимальный средний расход в день для включения в анализ ($)",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 1
            },
            "min_clicks": {
                "label": "Минимум кликов за период",
                "description": "Минимальное количество кликов за весь период анализа",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 10
            },
            "smoothing_window": {
                "label": "Окно сглаживания (дней)",
                "description": "Размер окна для скользящего среднего (сглаживание шума)",
                "type": "number",
                "min": 2,
                "max": 5,
                "step": 1
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "acceleration",
            "metric_label": "Ускорение",
            "metric_unit": "",
            "description": "Пороги критичности на основе ускорения динамики (положительные значения - ускорение роста, отрицательные - замедление)",
            "thresholds": {
                "severity_high": {
                    "label": "Высокое ускорение",
                    "description": "Ускорение выше этого значения считается высоким",
                    "type": "number",
                    "min": 2,
                    "max": 20,
                    "step": 1,
                    "default": 5
                },
                "severity_medium": {
                    "label": "Среднее ускорение",
                    "description": "Ускорение выше этого значения (но ниже высокого) считается средним",
                    "type": "number",
                    "min": 1,
                    "max": 10,
                    "step": 1,
                    "default": 2
                },
                "severity_high_negative": {
                    "label": "Высокое замедление",
                    "description": "Ускорение ниже этого значения считается высоким замедлением",
                    "type": "number",
                    "min": -20,
                    "max": -2,
                    "step": 1,
                    "default": -5
                },
                "severity_medium_negative": {
                    "label": "Среднее замедление",
                    "description": "Ускорение ниже этого значения (но выше высокого замедления) считается средним замедлением",
                    "type": "number",
                    "min": -10,
                    "max": -1,
                    "step": 1,
                    "default": -2
                }
            },
            "levels": [
                {"value": "high", "label": "Высокое ускорение", "color": "#10b981", "condition": "acceleration >= high"},
                {"value": "medium", "label": "Среднее ускорение", "color": "#3b82f6", "condition": "medium <= acceleration < high"},
                {"value": "low", "label": "Стабильно", "color": "#6b7280", "condition": "medium_negative < acceleration < medium"},
                {"value": "medium", "label": "Среднее замедление", "color": "#f59e0b", "condition": "high_negative < acceleration <= medium_negative"},
                {"value": "high", "label": "Высокое замедление", "color": "#ef4444", "condition": "acceleration <= high_negative"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ ускорения динамики через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные об ускорении кампаний
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_spend = config.params.get("min_spend", 1)
        min_clicks = config.params.get("min_clicks", 20)
        smoothing_window = config.params.get("smoothing_window", 3)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", 5)
        severity_medium_threshold = config.params.get("severity_medium", 2)
        severity_high_negative_threshold = config.params.get("severity_high_negative", -5)
        severity_medium_negative_threshold = config.params.get("severity_medium_negative", -2)

        # Валидация
        if days < 5:
            days = 5
        if days > 30:
            days = 30
        if smoothing_window < 2:
            smoothing_window = 2
        if smoothing_window > 5:
            smoothing_window = 5

        # Расчет дат (сегодня включительно)
        today = datetime.now().date()
        date_from = today - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем дневную статистику
            query = session.query(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date,
                func.sum(CampaignStatsDaily.cost).label('cost'),
                func.sum(CampaignStatsDaily.revenue).label('revenue'),
                func.sum(CampaignStatsDaily.clicks).label('clicks'),
                func.sum(CampaignStatsDaily.leads).label('leads')
            ).filter(
                CampaignStatsDaily.date >= date_from,
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

            # Анализируем ускорение для каждой кампании
            accelerating = []  # Ускоряющиеся
            stable_campaigns = []  # Стабильные
            decelerating = []  # Замедляющиеся

            for campaign_id, daily_data in campaigns_data.items():
                # Фильтрация: минимум данных
                if len(daily_data) < 3:
                    continue

                # Агрегируем общие метрики
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)

                # Фильтрация по порогам
                avg_daily_spend = total_cost / len(daily_data)
                if avg_daily_spend < min_spend:
                    continue
                if total_clicks < min_clicks:
                    continue

                # Вычисляем дневной ROI для каждого дня
                daily_roi = []
                for day in daily_data:
                    if day['cost'] > 0:
                        roi = (day['revenue'] - day['cost']) / day['cost'] * 100
                        daily_roi.append(roi)
                    else:
                        daily_roi.append(0)

                # Применяем сглаживание (moving average)
                smoothed_roi = self._moving_average(daily_roi, smoothing_window)

                # Вычисляем первую производную (скорость изменения)
                velocity = self._calculate_derivative(smoothed_roi)

                # Вычисляем вторую производную (ускорение)
                acceleration = self._calculate_derivative(velocity)

                # Если недостаточно данных для производных
                if not acceleration:
                    continue

                # Средние значения
                avg_velocity = sum(velocity) / len(velocity) if velocity else 0
                avg_acceleration = sum(acceleration) / len(acceleration) if acceleration else 0

                # Текущее ускорение (последнее значение)
                current_acceleration = acceleration[-1] if acceleration else 0

                # Средний ROI
                avg_roi = sum(smoothed_roi) / len(smoothed_roi) if smoothed_roi else 0
                current_roi = smoothed_roi[-1] if smoothed_roi else 0

                # Определяем категорию на основе настраиваемых порогов
                if current_acceleration > severity_medium_threshold:
                    category = "accelerating"
                    severity = "high" if current_acceleration > severity_high_threshold else "medium"
                elif current_acceleration < severity_medium_negative_threshold:
                    category = "decelerating"
                    severity = "high" if current_acceleration < severity_high_negative_threshold else "medium"
                else:
                    category = "stable"
                    severity = "low"

                # Формируем данные
                campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы"
                })

                campaign_acceleration = {
                    "campaign_id": campaign_id,
                    "binom_id": campaign_info['binom_id'],
                    "name": campaign_info['name'],
                    "group": campaign_info['group'],

                    # Агрегированные метрики
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "total_clicks": total_clicks,
                    "total_leads": total_leads,
                    "avg_roi": round(avg_roi, 2),
                    "current_roi": round(current_roi, 2),

                    # Динамика
                    "avg_velocity": round(avg_velocity, 2),
                    "current_velocity": round(velocity[-1] if velocity else 0, 2),
                    "avg_acceleration": round(avg_acceleration, 2),
                    "current_acceleration": round(current_acceleration, 2),

                    # Категория
                    "category": category,
                    "severity": severity,

                    # Дополнительно
                    "days_analyzed": len(daily_data)
                }

                # Распределяем по категориям
                if category == "accelerating":
                    accelerating.append(campaign_acceleration)
                elif category == "decelerating":
                    decelerating.append(campaign_acceleration)
                else:
                    stable_campaigns.append(campaign_acceleration)

            # Сортировка
            accelerating.sort(key=lambda x: x['current_acceleration'], reverse=True)
            decelerating.sort(key=lambda x: x['current_acceleration'])
            stable_campaigns.sort(key=lambda x: x['current_roi'], reverse=True)

            # Объединяем для общей таблицы
            all_campaigns = accelerating + stable_campaigns + decelerating

            return {
                "campaigns": all_campaigns,
                "accelerating": accelerating,
                "stable": stable_campaigns,
                "decelerating": decelerating,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_accelerating": len(accelerating),
                    "total_stable": len(stable_campaigns),
                    "total_decelerating": len(decelerating),
                    "avg_acceleration": round(
                        sum(c['current_acceleration'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "max_acceleration": round(
                        accelerating[0]['current_acceleration'], 2
                    ) if accelerating else 0,
                    "min_acceleration": round(
                        decelerating[0]['current_acceleration'], 2
                    ) if decelerating else 0
                },
                "period": {
                    "start": date_from.isoformat(),
                    "end": today.isoformat(),
                    "days": days
                },
                "thresholds": {
                    "min_spend": min_spend,
                    "min_clicks": min_clicks,
                    "smoothing_window": smoothing_window,
                    "severity_high": severity_high_threshold,
                    "severity_medium": severity_medium_threshold,
                    "severity_high_negative": severity_high_negative_threshold,
                    "severity_medium_negative": severity_medium_negative_threshold
                }
            }

    def _moving_average(self, data: List[float], window: int) -> List[float]:
        """
        Вычисляет скользящее среднее для сглаживания шума.

        Args:
            data: Исходные данные
            window: Размер окна

        Returns:
            List[float]: Сглаженные данные
        """
        if len(data) < window:
            return data

        smoothed = []
        for i in range(len(data)):
            if i < window - 1:
                # Для первых значений используем меньшее окно
                avg = sum(data[:i + 1]) / (i + 1)
            else:
                # Полное окно
                avg = sum(data[i - window + 1:i + 1]) / window
            smoothed.append(avg)

        return smoothed

    def _calculate_derivative(self, data: List[float]) -> List[float]:
        """
        Вычисляет производную (разность между соседними точками).

        Args:
            data: Исходные данные

        Returns:
            List[float]: Производная
        """
        if len(data) < 2:
            return []

        derivative = []
        for i in range(1, len(data)):
            diff = data[i] - data[i - 1]
            derivative.append(diff)

        return derivative

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
                        "label": "Ускорение",
                        "data": [c["current_acceleration"] for c in accelerating],
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
                        "label": "Ускорение",
                        "data": [c["current_acceleration"] for c in decelerating],
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
                "id": "acceleration_distribution",
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
                            "text": "Распределение по ускорению"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для значимых изменений ускорения.
        """
        alerts = []
        summary = raw_data["summary"]
        accelerating = raw_data["accelerating"]
        decelerating = raw_data["decelerating"]
        thresholds = raw_data.get("thresholds", {})

        # Получаем пороги для сообщений
        severity_high_threshold = thresholds.get("severity_high", 5)
        severity_high_negative_threshold = thresholds.get("severity_high_negative", -5)

        # Алерт о сильно ускоряющихся кампаниях
        strong_acceleration = [c for c in accelerating if c['current_acceleration'] > severity_high_threshold]
        if strong_acceleration:
            top_3 = strong_acceleration[:3]
            message = f"Обнаружено {len(strong_acceleration)} кампаний с сильным ускорением роста (>{severity_high_threshold})"
            message += "\n\nТоп-3 ускоряющихся:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: ускорение {camp['current_acceleration']:+.2f}, ROI {camp['current_roi']:.1f}%"

            alerts.append({
                "type": "strong_acceleration",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите увеличение бюджета для кампаний с сильным положительным ускорением",
                "campaigns_count": len(strong_acceleration)
            })

        # Алерт о сильно замедляющихся кампаниях
        strong_deceleration = [c for c in decelerating if c['current_acceleration'] < severity_high_negative_threshold]
        if strong_deceleration:
            top_3 = strong_deceleration[:3]
            message = f"ВНИМАНИЕ: {len(strong_deceleration)} кампаний с сильным замедлением (<{severity_high_negative_threshold})"
            message += "\n\nТоп-3 замедляющихся:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: ускорение {camp['current_acceleration']:+.2f}, ROI {camp['current_roi']:.1f}%"

            alerts.append({
                "type": "strong_deceleration",
                "severity": "high",
                "message": message,
                "recommended_action": "Срочно проверьте причины торможения роста и оптимизируйте кампании",
                "campaigns_count": len(strong_deceleration)
            })

        # Алерт об общем негативном ускорении
        if summary["avg_acceleration"] < -2:
            message = f"Среднее ускорение портфеля отрицательное: {summary['avg_acceleration']:.2f}"
            message += f"\nЗамедляющихся кампаний: {summary['total_decelerating']}"
            message += f"\nУскоряющихся кампаний: {summary['total_accelerating']}"

            alerts.append({
                "type": "negative_portfolio_acceleration",
                "severity": "high",
                "message": message,
                "recommended_action": "Общее торможение роста портфеля - требуется срочная оптимизация",
                "campaigns_count": summary["total_analyzed"]
            })

        return alerts
