"""
Модуль детекции разворота тренда с роста на падение
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
import math

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


class TrendReversalFinder(BaseModule):
    """
    Детектор разворота тренда.

    Выявляет точки разворота тренда, когда растущая кампания начинает падать:
    - Был рост ROI минимум 5 дней
    - Последние 2-3 дня идет снижение
    - Изменение наклона тренда > 30°
    - Подтверждение объемами (расход стабилен)

    Критично для своевременной корректировки стратегии.
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="trend_reversal_finder",
            name="Разворот тренда",
            category="trend_analysis",
            description="Обнаружение смены тренда с роста на падение для своевременной корректировки стратегии",
            detailed_description=(
                "Модуль выявляет точки разворота тренда, когда растущая кампания начинает падать. "
                "Анализирует историю ROI для обнаружения смены направления тренда с положительного на отрицательный. "
                "Использует анализ наклона линии тренда и подтверждение объемами. "
                "Критично для своевременной корректировки стратегии до значительных потерь."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="high",
            tags=["reversal", "trend", "roi", "decline", "warning"]
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
                "analysis_days": 10,  # общий период анализа (сегодня включительно)
                "growth_days": 3,  # минимум дней роста для определения растущего тренда
                "decline_days": 2,  # минимум дней снижения для определения разворота
                "min_slope_change_degrees": 20,  # минимальное изменение угла наклона (градусы)
                "volume_stability_threshold": 50,  # допустимое отклонение объема (%)
                "min_spend_per_day": 0.5,  # минимум $0.5 трат в день
                "min_clicks": 30,  # минимум 30 кликов за период
                "severity_critical_slope": 60,  # slope_change_degrees для critical severity
                "severity_critical_roi_drop": 30,  # roi_drop для critical severity
                "severity_high_slope": 45,  # slope_change_degrees для high severity
                "severity_high_roi_drop": 20,  # roi_drop для high severity
                "severity_medium_slope": 30,  # slope_change_degrees для medium severity
                "severity_medium_roi_drop": 10,  # roi_drop для medium severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.

        Returns:
            Dict с описаниями параметров
        """
        return {
            "analysis_days": {
                "label": "Дней для анализа",
                "description": "Общий период анализа для поиска разворота тренда (включая сегодня)",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "growth_days": {
                "label": "Минимум дней роста",
                "description": "Минимальное количество дней роста ROI для определения растущего тренда",
                "type": "number",
                "min": 3,
                "max": 365,
                "step": 1
            },
            "decline_days": {
                "label": "Минимум дней снижения",
                "description": "Минимальное количество дней снижения для определения разворота",
                "type": "number",
                "min": 2,
                "max": 365,
                "step": 1
            },
            "min_slope_change_degrees": {
                "label": "Изменение наклона",
                "description": "Минимальное изменение угла наклона тренда для определения разворота (градусы)",
                "type": "number",
                "min": 10,
                "max": 90,
                "step": 5
            },
            "volume_stability_threshold": {
                "label": "Стабильность объема",
                "description": "Допустимое отклонение объема расходов для подтверждения разворота (%)",
                "type": "number",
                "min": 10,
                "max": 50,
                "step": 5
            },
            "min_spend_per_day": {
                "label": "Минимальный расход в день",
                "description": "Минимальный расход для включения кампании в анализ ($ в день)",
                "type": "number",
                "min": 0.5,
                "max": 10000,
                "step": 0.5
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов за весь период анализа",
                "type": "number",
                "min": 50,
                "max": 10000,
                "step": 10
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "reversal",
            "metric_label": "Разворот тренда",
            "metric_unit": "",
            "description": "Пороги критичности на основе силы разворота (комбинация изменения угла наклона и падения ROI)",
            "thresholds": {
                "severity_critical_slope": {
                    "label": "Критичный угол наклона",
                    "description": "Изменение угла наклона (градусы) для критичного разворота (используется совместно с критичным падением ROI)",
                    "type": "number",
                    "min": 45,
                    "max": 90,
                    "step": 5,
                    "default": 60
                },
                "severity_critical_roi_drop": {
                    "label": "Критичное падение ROI",
                    "description": "Падение ROI (%) для критичного разворота (используется совместно с критичным углом)",
                    "type": "number",
                    "min": 20,
                    "max": 100,
                    "step": 5,
                    "default": 30
                },
                "severity_high_slope": {
                    "label": "Высокий угол наклона",
                    "description": "Изменение угла наклона для высокого разворота (используется с OR логикой с падением ROI)",
                    "type": "number",
                    "min": 30,
                    "max": 90,
                    "step": 5,
                    "default": 45
                },
                "severity_high_roi_drop": {
                    "label": "Высокое падение ROI",
                    "description": "Падение ROI для высокого разворота (используется с OR логикой с углом)",
                    "type": "number",
                    "min": 15,
                    "max": 50,
                    "step": 5,
                    "default": 20
                },
                "severity_medium_slope": {
                    "label": "Средний угол наклона",
                    "description": "Изменение угла наклона для среднего разворота (используется с OR логикой с падением ROI)",
                    "type": "number",
                    "min": 20,
                    "max": 60,
                    "step": 5,
                    "default": 30
                },
                "severity_medium_roi_drop": {
                    "label": "Среднее падение ROI",
                    "description": "Падение ROI для среднего разворота (используется с OR логикой с углом)",
                    "type": "number",
                    "min": 5,
                    "max": 30,
                    "step": 5,
                    "default": 10
                }
            },
            "levels": [
                {"value": "critical", "label": "Критичный разворот", "color": "#dc2626", "condition": "slope >= critical_slope AND roi_drop >= critical_roi_drop"},
                {"value": "high", "label": "Высокий разворот", "color": "#ef4444", "condition": "slope >= high_slope OR roi_drop >= high_roi_drop"},
                {"value": "medium", "label": "Средний разворот", "color": "#f59e0b", "condition": "slope >= medium_slope OR roi_drop >= medium_roi_drop"},
                {"value": "low", "label": "Слабый разворот", "color": "#fbbf24", "condition": "otherwise"}
            ]
        }

    def _calculate_linear_regression(self, data_points: List[float]) -> Dict[str, float]:
        """
        Вычисляет параметры линейной регрессии.

        Args:
            data_points: Список значений

        Returns:
            Dict с параметрами: slope (наклон), intercept, r_squared
        """
        n = len(data_points)
        if n < 2:
            return {"slope": 0, "intercept": 0, "r_squared": 0, "angle_degrees": 0}

        # x = [0, 1, 2, ..., n-1]
        x_values = list(range(n))
        y_values = data_points

        # Средние значения
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        # Вычисление наклона и пересечения
        numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return {"slope": 0, "intercept": y_mean, "r_squared": 0, "angle_degrees": 0}

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # R-squared
        ss_res = sum((y_values[i] - (slope * x_values[i] + intercept)) ** 2 for i in range(n))
        ss_tot = sum((y_values[i] - y_mean) ** 2 for i in range(n))

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # Угол наклона в градусах
        angle_radians = math.atan(slope)
        angle_degrees = math.degrees(angle_radians)

        return {
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_squared,
            "angle_degrees": angle_degrees
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ разворота тренда через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с разворотом тренда
        """
        # Получение параметров
        analysis_days = config.params.get("analysis_days", 14)
        growth_days = config.params.get("growth_days", 5)
        decline_days = config.params.get("decline_days", 2)
        min_slope_change_degrees = config.params.get("min_slope_change_degrees", 30)
        volume_stability_threshold = config.params.get("volume_stability_threshold", 20)
        min_spend_per_day = config.params.get("min_spend_per_day", 1)
        min_clicks = config.params.get("min_clicks", 100)

        # Получение настраиваемых порогов severity
        severity_critical_slope = config.params.get("severity_critical_slope", 60)
        severity_critical_roi_drop = config.params.get("severity_critical_roi_drop", 30)
        severity_high_slope = config.params.get("severity_high_slope", 45)
        severity_high_roi_drop = config.params.get("severity_high_roi_drop", 20)
        severity_medium_slope = config.params.get("severity_medium_slope", 30)
        severity_medium_roi_drop = config.params.get("severity_medium_roi_drop", 10)

        # Валидация параметров
        if analysis_days < 7 or analysis_days > 30:
            analysis_days = 14
        if growth_days < 3 or growth_days > 14:
            growth_days = 5
        if decline_days < 2 or decline_days > 7:
            decline_days = 2
        if min_slope_change_degrees < 10 or min_slope_change_degrees > 90:
            min_slope_change_degrees = 30
        if volume_stability_threshold < 10 or volume_stability_threshold > 50:
            volume_stability_threshold = 20

        # Расчет дат
        today = datetime.now().date()
        date_from = today - timedelta(days=analysis_days - 1)

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

            # Анализируем разворот тренда
            reversal_campaigns = []
            total_campaigns_analyzed = 0
            campaigns_growing = 0
            campaigns_declining = 0
            campaigns_stable = 0
            campaigns_filtered_out = 0  # Кампании, не прошедшие пороги

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < growth_days + decline_days:
                    campaigns_filtered_out += 1
                    continue

                # Агрегированная статистика
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)

                # Фильтрация по минимальным порогам
                avg_daily_spend = total_cost / len(daily_data)
                if avg_daily_spend < min_spend_per_day or total_clicks < min_clicks:
                    campaigns_filtered_out += 1
                    continue

                # Теперь увеличиваем счетчик проанализированных (прошедших пороги)
                total_campaigns_analyzed += 1

                # Вычисляем ROI для каждого дня
                daily_roi = []
                daily_costs = []
                for d in daily_data:
                    roi = ((d['revenue'] - d['cost']) / d['cost'] * 100) if d['cost'] > 0 else 0
                    daily_roi.append(roi)
                    daily_costs.append(d['cost'])

                # Проверяем стабильность объемов
                avg_cost = sum(daily_costs) / len(daily_costs)
                cost_variance = sum(abs(c - avg_cost) / avg_cost * 100 for c in daily_costs) / len(daily_costs)

                if cost_variance > volume_stability_threshold:
                    # Объемы нестабильны - считаем как стабильные (не подходят для анализа разворота)
                    campaigns_stable += 1
                    continue

                # Ищем период роста (минимум growth_days дней роста подряд)
                growth_periods = []
                current_growth_streak = []

                for i in range(1, len(daily_roi)):
                    if daily_roi[i] > daily_roi[i - 1]:
                        # Если streak только начинается, добавляем оба дня (i-1 и i)
                        if not current_growth_streak:
                            current_growth_streak = [i - 1, i]
                        # Если streak продолжается, добавляем только текущий день
                        elif current_growth_streak[-1] == i - 1:
                            current_growth_streak.append(i)
                        # Если был разрыв, начинаем новый streak
                        else:
                            if len(current_growth_streak) >= growth_days:
                                growth_periods.append(current_growth_streak.copy())
                            current_growth_streak = [i - 1, i]
                    else:
                        # Рост закончился
                        if len(current_growth_streak) >= growth_days:
                            growth_periods.append(current_growth_streak.copy())
                        current_growth_streak = []

                # Проверяем последний streak
                if len(current_growth_streak) >= growth_days:
                    growth_periods.append(current_growth_streak.copy())

                # Если не было периода роста, пропускаем
                if not growth_periods:
                    campaigns_stable += 1
                    continue

                # Находим последний период роста
                last_growth_period = growth_periods[-1]
                growth_end_idx = last_growth_period[-1]

                # Вычисляем линейную регрессию для периода роста
                growth_roi_values = [daily_roi[i] for i in last_growth_period]
                growth_regression = self._calculate_linear_regression(growth_roi_values)

                # Проверяем значимость тренда роста
                # Для коротких периодов (3-4 дня) используем более мягкий порог R² > 0.3
                # Для длинных периодов (5+ дней) требуем R² > 0.5
                min_r_squared = 0.3 if len(last_growth_period) <= 4 else 0.5
                if growth_regression['r_squared'] < min_r_squared:
                    campaigns_stable += 1
                    continue

                # Проверяем есть ли данные после роста для анализа снижения
                if growth_end_idx >= len(daily_roi) - decline_days:
                    campaigns_growing += 1
                    continue

                # Анализируем период после роста
                decline_period = list(range(growth_end_idx + 1, len(daily_roi)))

                if len(decline_period) < decline_days:
                    campaigns_growing += 1
                    continue

                # Проверяем снижение ROI в последние decline_days дней
                recent_decline_period = decline_period[-decline_days:]
                is_declining = True
                for i in range(1, len(recent_decline_period)):
                    idx = recent_decline_period[i]
                    prev_idx = recent_decline_period[i - 1]
                    if daily_roi[idx] >= daily_roi[prev_idx]:
                        is_declining = False
                        break

                if not is_declining:
                    campaigns_growing += 1
                    continue

                # Вычисляем линейную регрессию для периода снижения
                decline_roi_values = [daily_roi[i] for i in recent_decline_period]
                decline_regression = self._calculate_linear_regression(decline_roi_values)

                # Вычисляем изменение угла наклона
                slope_change_degrees = abs(growth_regression['angle_degrees'] - decline_regression['angle_degrees'])

                # Проверяем изменение наклона
                if slope_change_degrees < min_slope_change_degrees:
                    campaigns_declining += 1
                    continue

                # Формируем данные о развороте
                campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы"
                })

                # Вычисляем общий ROI
                total_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
                total_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0

                # ROI в точке разворота и текущий
                reversal_point_roi = daily_roi[growth_end_idx]
                current_roi = daily_roi[-1]
                roi_drop = reversal_point_roi - current_roi

                # Сила разворота (0-100) - комбинация угла наклона и падения ROI
                # Компонент 1: Изменение угла (0-60 баллов)
                # 20° = 0 баллов, 180° = 60 баллов (линейная шкала от порога)
                angle_component = min(60, max(0, (slope_change_degrees - 20) / 160 * 60))

                # Компонент 2: Падение ROI (0-40 баллов)
                # Учитываем абсолютное и относительное падение
                if abs(reversal_point_roi) > 10:
                    # Для значимого ROI считаем относительное падение
                    relative_drop = min(100, (abs(roi_drop) / abs(reversal_point_roi)) * 100)
                    roi_component = min(40, relative_drop * 0.4)
                else:
                    # Для малого ROI считаем абсолютное падение
                    roi_component = min(40, abs(roi_drop) * 0.8)

                reversal_strength = round(angle_component + roi_component, 2)

                # Определяем severity на основе настраиваемых порогов
                if slope_change_degrees >= severity_critical_slope and roi_drop > severity_critical_roi_drop:
                    severity = "critical"  # Очень сильный разворот
                elif slope_change_degrees >= severity_high_slope or roi_drop > severity_high_roi_drop:
                    severity = "high"  # Сильный разворот
                elif slope_change_degrees >= severity_medium_slope or roi_drop > severity_medium_roi_drop:
                    severity = "medium"  # Умеренный разворот
                else:
                    severity = "low"  # Слабый разворот

                reversal_data = {
                    "campaign_id": campaign_id,
                    "binom_id": campaign_info['binom_id'],
                    "name": campaign_info['name'],
                    "group": campaign_info['group'],

                    # Общая статистика
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "total_clicks": total_clicks,
                    "total_leads": total_leads,
                    "avg_roi": round(total_roi, 2),

                    # Период роста
                    "growth_days_count": len(last_growth_period),
                    "growth_start_date": daily_data[last_growth_period[0]]['date'].isoformat(),
                    "growth_end_date": daily_data[growth_end_idx]['date'].isoformat(),
                    "growth_slope": round(growth_regression['slope'], 2),
                    "growth_angle": round(growth_regression['angle_degrees'], 2),
                    "growth_r_squared": round(growth_regression['r_squared'], 2),

                    # Период снижения
                    "decline_days_count": len(recent_decline_period),
                    "decline_start_date": daily_data[recent_decline_period[0]]['date'].isoformat(),
                    "decline_slope": round(decline_regression['slope'], 2),
                    "decline_angle": round(decline_regression['angle_degrees'], 2),

                    # Разворот
                    "reversal_point_roi": round(reversal_point_roi, 2),
                    "current_roi": round(current_roi, 2),
                    "roi_drop": round(roi_drop, 2),
                    "slope_change_degrees": round(slope_change_degrees, 2),
                    "reversal_strength": round(reversal_strength, 2),
                    "volume_stability": round(100 - cost_variance, 2),

                    # Severity
                    "severity": severity
                }

                reversal_campaigns.append(reversal_data)

            # Сортировка по силе разворота (наиболее критичные первыми)
            reversal_campaigns.sort(key=lambda x: x['reversal_strength'], reverse=True)

            return {
                "reversal_campaigns": reversal_campaigns,
                "summary": {
                    "total_reversals": len(reversal_campaigns),
                    "total_analyzed": total_campaigns_analyzed,
                    "total_growing": campaigns_growing,
                    "total_declining": campaigns_declining,
                    "total_stable": campaigns_stable,
                    "total_filtered_out": campaigns_filtered_out,
                    "critical_reversals": len([c for c in reversal_campaigns if c['severity'] == 'critical']),
                    "high_reversals": len([c for c in reversal_campaigns if c['severity'] == 'high']),
                    "avg_reversal_strength": round(
                        sum(c['reversal_strength'] for c in reversal_campaigns) / len(reversal_campaigns), 2
                    ) if reversal_campaigns else 0,
                    "avg_roi_drop": round(
                        sum(c['roi_drop'] for c in reversal_campaigns) / len(reversal_campaigns), 2
                    ) if reversal_campaigns else 0,
                    "avg_slope_change": round(
                        sum(c['slope_change_degrees'] for c in reversal_campaigns) / len(reversal_campaigns), 2
                    ) if reversal_campaigns else 0
                },
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": today.isoformat(),
                    "days": analysis_days
                },
                "thresholds": {
                    "min_spend_per_day": min_spend_per_day,
                    "min_clicks": min_clicks,
                    "growth_days": growth_days,
                    "decline_days": decline_days,
                    "min_slope_change_degrees": min_slope_change_degrees,
                    "volume_stability_threshold": volume_stability_threshold,
                    "severity_critical_slope": severity_critical_slope,
                    "severity_critical_roi_drop": severity_critical_roi_drop,
                    "severity_high_slope": severity_high_slope,
                    "severity_high_roi_drop": severity_high_roi_drop,
                    "severity_medium_slope": severity_medium_slope,
                    "severity_medium_roi_drop": severity_medium_roi_drop
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
        reversals = raw_data["reversal_campaigns"][:10]

        charts = []

        # График силы разворота
        if reversals:
            charts.append({
                "id": "reversal_strength_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in reversals],
                    "datasets": [{
                        "label": "Сила разворота",
                        "data": [c["reversal_strength"] for c in reversals],
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
                            "text": "Топ-10 кампаний с разворотом тренда"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "max": 100
                        }
                    }
                }
            })

            # График падения ROI
            charts.append({
                "id": "roi_drop_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in reversals],
                    "datasets": [{
                        "label": "Падение ROI (%)",
                        "data": [c["roi_drop"] for c in reversals],
                        "backgroundColor": "rgba(251, 146, 60, 0.5)",
                        "borderColor": "rgba(251, 146, 60, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Падение ROI от точки разворота"
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

            # График изменения угла наклона
            charts.append({
                "id": "slope_change_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in reversals],
                    "datasets": [{
                        "label": "Изменение наклона (градусы)",
                        "data": [c["slope_change_degrees"] for c in reversals],
                        "backgroundColor": "rgba(168, 85, 247, 0.5)",
                        "borderColor": "rgba(168, 85, 247, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Изменение угла наклона тренда"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "max": 90
                        }
                    }
                }
            })

        # Pie chart: Распределение по severity
        summary = raw_data["summary"]
        if summary["total_reversals"] > 0:
            charts.append({
                "id": "reversal_severity_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Критичные", "Высокие", "Средние", "Низкие"],
                    "datasets": [{
                        "data": [
                            len([c for c in reversals if c['severity'] == 'critical']),
                            len([c for c in reversals if c['severity'] == 'high']),
                            len([c for c in reversals if c['severity'] == 'medium']),
                            len([c for c in reversals if c['severity'] == 'low'])
                        ],
                        "backgroundColor": [
                            "rgba(220, 38, 38, 0.8)",
                            "rgba(239, 68, 68, 0.8)",
                            "rgba(251, 146, 60, 0.8)",
                            "rgba(251, 191, 36, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по критичности"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для разворотов тренда.
        """
        alerts = []
        summary = raw_data["summary"]
        reversals = raw_data["reversal_campaigns"]

        # Алерт о критичных разворотах
        critical_reversals = [c for c in reversals if c['severity'] == 'critical']
        if critical_reversals:
            top_3 = critical_reversals[:3]
            message = f"КРИТИЧНО: Обнаружено {len(critical_reversals)} кампаний с сильным разворотом тренда!"
            message += "\n\nТоп-3 критичных разворота:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: ROI упал с {camp['reversal_point_roi']:.1f}% до {camp['current_roi']:.1f}% (падение {camp['roi_drop']:.1f}%)"

            alerts.append({
                "type": "critical_reversal",
                "severity": "critical",
                "message": message,
                "recommended_action": "СРОЧНО приостановите эти кампании и проанализируйте причины падения",
                "campaigns_count": len(critical_reversals)
            })

        # Алерт о высоких разворотах
        high_reversals = [c for c in reversals if c['severity'] == 'high']
        if high_reversals:
            top_3 = high_reversals[:3]
            message = f"ВНИМАНИЕ: {len(high_reversals)} кампаний с сильным разворотом тренда"
            message += "\n\nТоп-3 разворота:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: изменение наклона {camp['slope_change_degrees']:.1f}°, падение ROI {camp['roi_drop']:.1f}%"

            alerts.append({
                "type": "high_reversal",
                "severity": "high",
                "message": message,
                "recommended_action": "Оптимизируйте кампании или снизьте бюджет до выявления причин падения",
                "campaigns_count": len(high_reversals)
            })

        # Алерт о кампаниях ушедших в минус
        negative_reversals = [c for c in reversals if c['current_roi'] < 0 and c['reversal_point_roi'] > 0]
        if negative_reversals:
            message = f"УБЫТОК: {len(negative_reversals)} кампаний упали из прибыли в убыток!"
            top_3 = negative_reversals[:3]
            message += "\n\nТоп-3:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: из +{camp['reversal_point_roi']:.1f}% в {camp['current_roi']:.1f}%"

            alerts.append({
                "type": "profit_to_loss_reversal",
                "severity": "critical",
                "message": message,
                "recommended_action": "Немедленно остановите убыточные кампании до выяснения причин",
                "campaigns_count": len(negative_reversals)
            })

        return alerts
