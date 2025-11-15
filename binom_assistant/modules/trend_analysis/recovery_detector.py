"""
Модуль детекции восстановления кампаний после просадки
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


class RecoveryDetector(BaseModule):
    """
    Детектор восстановления кампаний.

    Находит кампании, которые начали восстанавливаться после периода плохих показателей:
    - Был период с ROI < -30% (минимум 3 дня)
    - Текущий ROI растет 2+ дня подряд
    - Текущий ROI > ROI минимума + 20%
    - Положительная динамика CR

    Помогает не упустить момент возвращения к прибыльности.
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="recovery_detector",
            name="Восстановление",
            category="trend_analysis",
            description="Поиск восстанавливающихся после просадки кампаний",
            detailed_description=(
                "Модуль обнаруживает кампании, которые начали восстанавливаться после периода плохих показателей. "
                "Анализирует историю ROI для выявления просадок и последующего роста. "
                "Помогает не упустить момент возвращения к прибыльности и вовремя возобновить инвестиции."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["recovery", "roi", "trend", "reversal"]
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
                "analysis_days": 14,  # общий период анализа
                "min_bad_days": 3,  # минимум дней в просадке
                "bad_roi_threshold": -30,  # порог ROI для определения просадки (%)
                "recovery_days": 2,  # минимум дней подряд роста для восстановления
                "recovery_improvement": 20,  # минимальное улучшение от дна (%)
                "min_spend": 3,  # минимум $3 трат за период
                "min_clicks": 50,  # минимум 50 кликов за период
                "severity_high": 70,  # recovery_strength для high severity (сильное восстановление)
                "severity_medium": 50,  # recovery_strength для medium severity (умеренное восстановление)
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
                "description": "Общий период анализа для поиска просадок и восстановления (включая сегодня)",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "min_bad_days": {
                "label": "Минимум дней в просадке",
                "description": "Минимальное количество дней подряд с плохим ROI для определения просадки",
                "type": "number",
                "min": 2,
                "max": 365,
                "step": 1
            },
            "bad_roi_threshold": {
                "label": "Порог плохого ROI",
                "description": "ROI ниже этого значения считается просадкой (%)",
                "type": "number",
                "min": -100,
                "max": 0,
                "step": 5
            },
            "recovery_days": {
                "label": "Дней роста для восстановления",
                "description": "Минимум дней подряд роста ROI для определения восстановления",
                "type": "number",
                "min": 1,
                "max": 365,
                "step": 1
            },
            "recovery_improvement": {
                "label": "Улучшение от дна",
                "description": "Минимальное улучшение ROI от минимума для подтверждения восстановления (%)",
                "type": "number",
                "min": 10,
                "max": 100,
                "step": 5
            },
            "min_spend": {
                "label": "Минимальный расход",
                "description": "Минимальный расход для включения кампании в анализ ($)",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 1
            },
            "min_clicks": {
                "label": "Минимум кликов",
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
            "metric": "recovery_strength",
            "metric_label": "Сила восстановления",
            "metric_unit": "",
            "description": "Пороги критичности на основе силы восстановления кампании после просадки (0-100)",
            "thresholds": {
                "severity_high": {
                    "label": "Сильное восстановление",
                    "description": "Сила восстановления выше этого значения считается сильной (особенно если ROI > 0)",
                    "type": "number",
                    "min": 50,
                    "max": 100,
                    "step": 5,
                    "default": 70
                },
                "severity_medium": {
                    "label": "Умеренное восстановление",
                    "description": "Сила восстановления выше этого значения (но ниже сильного) считается умеренной",
                    "type": "number",
                    "min": 30,
                    "max": 80,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "high", "label": "Сильное восстановление", "color": "#10b981", "condition": "recovery_strength >= high AND current_roi > 0"},
                {"value": "medium", "label": "Умеренное восстановление", "color": "#3b82f6", "condition": "recovery_strength >= medium"},
                {"value": "low", "label": "Слабое восстановление", "color": "#fbbf24", "condition": "recovery_strength < medium"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ восстанавливающихся кампаний через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о восстанавливающихся кампаниях
        """
        # Получение параметров
        analysis_days = config.params.get("analysis_days", 14)
        min_bad_days = config.params.get("min_bad_days", 3)
        bad_roi_threshold = config.params.get("bad_roi_threshold", -30)
        recovery_days = config.params.get("recovery_days", 2)
        recovery_improvement = config.params.get("recovery_improvement", 20)
        min_spend = config.params.get("min_spend", 3)
        min_clicks = config.params.get("min_clicks", 50)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", 70)
        severity_medium_threshold = config.params.get("severity_medium", 50)

        # Валидация параметров
        if analysis_days < 7 or analysis_days > 30:
            analysis_days = 14
        if min_bad_days < 2 or min_bad_days > 10:
            min_bad_days = 3
        if bad_roi_threshold > 0 or bad_roi_threshold < -100:
            bad_roi_threshold = -30
        if recovery_days < 1 or recovery_days > 7:
            recovery_days = 2
        if recovery_improvement < 10 or recovery_improvement > 100:
            recovery_improvement = 20

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

            # Анализируем восстановление
            recovering_campaigns = []
            total_campaigns_analyzed = 0
            campaigns_in_drawdown = 0
            campaigns_stable = 0

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < min_bad_days + recovery_days:
                    continue

                total_campaigns_analyzed += 1

                # Агрегированная статистика
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)

                # Фильтрация по минимальным порогам
                if total_cost < min_spend or total_clicks < min_clicks:
                    continue

                # Вычисляем ROI для каждого дня
                daily_roi = []
                for d in daily_data:
                    roi = ((d['revenue'] - d['cost']) / d['cost'] * 100) if d['cost'] > 0 else 0
                    cr = (d['leads'] / d['clicks'] * 100) if d['clicks'] > 0 else 0
                    daily_roi.append({
                        'date': d['date'],
                        'roi': roi,
                        'cr': cr,
                        'cost': d['cost'],
                        'revenue': d['revenue']
                    })

                # Ищем период просадки (ROI < bad_roi_threshold минимум min_bad_days дней)
                bad_periods = []
                current_bad_streak = []

                for i, day in enumerate(daily_roi):
                    if day['roi'] < bad_roi_threshold:
                        current_bad_streak.append(i)
                    else:
                        if len(current_bad_streak) >= min_bad_days:
                            bad_periods.append(current_bad_streak.copy())
                        current_bad_streak = []

                # Проверяем последний streak
                if len(current_bad_streak) >= min_bad_days:
                    bad_periods.append(current_bad_streak.copy())

                # Если не было просадки, пропускаем
                if not bad_periods:
                    campaigns_stable += 1
                    continue

                # Находим последнюю просадку
                last_bad_period = bad_periods[-1]
                bad_period_end_idx = last_bad_period[-1]

                # Находим минимальный ROI в просадке
                min_roi = min(daily_roi[i]['roi'] for i in last_bad_period)
                min_roi_idx = None
                for i in last_bad_period:
                    if daily_roi[i]['roi'] == min_roi:
                        min_roi_idx = i
                        break

                # Проверяем есть ли данные после просадки для анализа восстановления
                if bad_period_end_idx >= len(daily_roi) - recovery_days:
                    campaigns_in_drawdown += 1
                    continue

                # Анализируем период после просадки
                recovery_period = daily_roi[bad_period_end_idx + 1:]

                if len(recovery_period) < recovery_days:
                    campaigns_in_drawdown += 1
                    continue

                # Проверяем рост ROI в последние recovery_days дней
                recent_days = recovery_period[-recovery_days:]
                is_growing = True
                for i in range(1, len(recent_days)):
                    if recent_days[i]['roi'] <= recent_days[i-1]['roi']:
                        is_growing = False
                        break

                if not is_growing:
                    campaigns_in_drawdown += 1
                    continue

                # Текущий ROI
                current_roi = recent_days[-1]['roi']

                # Проверяем улучшение от минимума
                roi_improvement = current_roi - min_roi

                if roi_improvement < recovery_improvement:
                    campaigns_in_drawdown += 1
                    continue

                # Проверяем положительную динамику CR
                # Сравниваем среднюю CR в просадке и текущую CR
                bad_period_cr = sum(daily_roi[i]['cr'] for i in last_bad_period) / len(last_bad_period)
                current_cr = recent_days[-1]['cr']
                cr_improvement = current_cr - bad_period_cr

                # Формируем данные о восстановлении
                campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы"
                })

                # Вычисляем общий ROI
                total_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
                total_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0

                # Сила восстановления (0-100)
                recovery_strength = min(100, (roi_improvement / recovery_improvement) * 50 +
                                       (max(0, cr_improvement) / max(0.1, bad_period_cr)) * 50)

                # Определяем severity на основе настраиваемых порогов
                if recovery_strength >= severity_high_threshold and current_roi > 0:
                    severity = "high"  # Сильное восстановление к прибыли
                elif recovery_strength >= severity_medium_threshold:
                    severity = "medium"  # Умеренное восстановление
                else:
                    severity = "low"  # Слабое восстановление

                recovery_data = {
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

                    # Просадка
                    "min_roi": round(min_roi, 2),
                    "bad_period_days": len(last_bad_period),
                    "bad_period_start": daily_roi[last_bad_period[0]]['date'].isoformat(),
                    "bad_period_end": daily_roi[last_bad_period[-1]]['date'].isoformat(),

                    # Восстановление
                    "current_roi": round(current_roi, 2),
                    "roi_improvement": round(roi_improvement, 2),
                    "recovery_days_count": len(recovery_period),
                    "recovery_strength": round(recovery_strength, 2),

                    # CR
                    "current_cr": round(current_cr, 2),
                    "cr_improvement": round(cr_improvement, 2),

                    # Severity
                    "severity": severity
                }

                recovering_campaigns.append(recovery_data)

            # Сортировка по силе восстановления
            recovering_campaigns.sort(key=lambda x: x['recovery_strength'], reverse=True)

            return {
                "recovering_campaigns": recovering_campaigns,
                "summary": {
                    "total_recovering": len(recovering_campaigns),
                    "total_analyzed": total_campaigns_analyzed,
                    "total_in_drawdown": campaigns_in_drawdown,
                    "total_stable": campaigns_stable,
                    "avg_recovery_strength": round(
                        sum(c['recovery_strength'] for c in recovering_campaigns) / len(recovering_campaigns), 2
                    ) if recovering_campaigns else 0,
                    "strong_recoveries": len([c for c in recovering_campaigns if c['severity'] == 'high']),
                    "avg_roi_improvement": round(
                        sum(c['roi_improvement'] for c in recovering_campaigns) / len(recovering_campaigns), 2
                    ) if recovering_campaigns else 0
                },
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": today.isoformat(),
                    "days": analysis_days
                },
                "thresholds": {
                    "min_spend": min_spend,
                    "min_clicks": min_clicks,
                    "bad_roi_threshold": bad_roi_threshold,
                    "min_bad_days": min_bad_days,
                    "recovery_days": recovery_days,
                    "recovery_improvement": recovery_improvement,
                    "severity_high": severity_high_threshold,
                    "severity_medium": severity_medium_threshold
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
        recovering = raw_data["recovering_campaigns"][:10]

        charts = []

        # График силы восстановления
        if recovering:
            charts.append({
                "id": "recovery_strength_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in recovering],
                    "datasets": [{
                        "label": "Сила восстановления",
                        "data": [c["recovery_strength"] for c in recovering],
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
                            "text": "Топ-10 восстанавливающихся кампаний"
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

            # График улучшения ROI
            charts.append({
                "id": "roi_improvement_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in recovering],
                    "datasets": [{
                        "label": "Улучшение ROI (%)",
                        "data": [c["roi_improvement"] for c in recovering],
                        "backgroundColor": "rgba(59, 130, 246, 0.5)",
                        "borderColor": "rgba(59, 130, 246, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Улучшение ROI от минимума"
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

        # Pie chart: Распределение по силе восстановления
        summary = raw_data["summary"]
        if summary["total_recovering"] > 0:
            charts.append({
                "id": "recovery_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Сильное", "Умеренное", "Слабое"],
                    "datasets": [{
                        "data": [
                            len([c for c in recovering if c['severity'] == 'high']),
                            len([c for c in recovering if c['severity'] == 'medium']),
                            len([c for c in recovering if c['severity'] == 'low'])
                        ],
                        "backgroundColor": [
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(59, 130, 246, 0.8)",
                            "rgba(251, 191, 36, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по силе восстановления"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для восстанавливающихся кампаний.
        """
        alerts = []
        summary = raw_data["summary"]
        recovering = raw_data["recovering_campaigns"]

        # Алерт о сильных восстановлениях
        strong_recoveries = [c for c in recovering if c['severity'] == 'high']
        if strong_recoveries:
            top_3 = strong_recoveries[:3]
            message = f"Обнаружено {len(strong_recoveries)} кампаний с сильным восстановлением"
            message += "\n\nТоп-3 восстанавливающихся:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: ROI {camp['current_roi']:.1f}% (было {camp['min_roi']:.1f}%), улучшение {camp['roi_improvement']:.1f}%"

            alerts.append({
                "type": "strong_recovery",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите возобновление инвестиций в восстанавливающиеся кампании",
                "campaigns_count": len(strong_recoveries)
            })

        # Алерт о кампаниях вышедших в плюс
        profitable_recoveries = [c for c in recovering if c['current_roi'] > 0 and c['min_roi'] < 0]
        if profitable_recoveries:
            message = f"УСПЕХ: {len(profitable_recoveries)} кампаний вышли из убытка в прибыль!"
            top_3 = profitable_recoveries[:3]
            message += "\n\nТоп-3:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: из {camp['min_roi']:.1f}% в {camp['current_roi']:.1f}%"

            alerts.append({
                "type": "profitable_recovery",
                "severity": "high",
                "message": message,
                "recommended_action": "Эти кампании показали способность к восстановлению - увеличьте бюджет",
                "campaigns_count": len(profitable_recoveries)
            })

        return alerts
