"""
Модуль поиска кампаний с резким падением качества трафика
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
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


class TrafficQualityCrash(BaseModule):
    """
    Детектор резкого падения качества трафика.

    Обнаруживает внезапное ухудшение CR при стабильном объеме трафика,
    что указывает на проблемы с качеством. Критично для раннего выявления
    проблем с источником.

    Критерии:
    - Падение CR > 40% за последние 7 дней (настраивается)
    - Объем трафика стабилен (±20%) (настраивается)
    - Минимум 500 кликов за период (настраивается)
    - Отклонение от недельного среднего > 2σ (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="traffic_quality_crash",
            name="Падение качества",
            category="critical_alerts",
            description="Обнаруживает падение качества трафика кампании (CR)",
            detailed_description="Модуль выявляет внезапное ухудшение конверсии при стабильном объеме трафика. Критично для раннего обнаружения проблем с источником или изменений в качестве аудитории.",
            version="1.1.0",  # исправлены дефолтные параметры согласно ТЗ
            author="Binom Assistant",
            priority="critical",
            tags=["cr", "quality", "traffic", "critical"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Критический модуль - автозапуск выключен по умолчанию
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=30,
            cache_ttl_seconds=3600,
            params={
                "cr_drop_threshold": 40,  # падение CR > 40% (согласно ТЗ)
                "traffic_stability": 20,  # стабильность трафика ±20% (согласно ТЗ)
                "min_clicks": 500,  # минимум 500 кликов за период (согласно ТЗ)
                "sigma_threshold": 2.0,  # отклонение > 2σ (согласно ТЗ)
                "days": 7,  # период анализа: 7 дней
                "severity_critical": 70,  # процент падения CR для critical severity
                "severity_high": 50  # процент падения CR для high severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "cr_drop_threshold": {
                "label": "Порог падения CR (%)",
                "description": "Минимальное падение CR для включения в анализ",
                "type": "number",
                "min": 10,
                "max": 90,
                "step": 5
            },
            "traffic_stability": {
                "label": "Стабильность трафика (±%)",
                "description": "Допустимое отклонение объема трафика между периодами",
                "type": "number",
                "min": 10,
                "max": 50,
                "step": 5
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов за период для анализа",
                "type": "number",
                "min": 100,
                "max": 10000,
                "step": 100
            },
            "sigma_threshold": {
                "label": "Порог сигма",
                "description": "Минимальное отклонение в сигмах для детекции",
                "type": "number",
                "min": 1.0,
                "max": 5.0,
                "step": 0.5
            },
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для текущего и предыдущего периода",
                "type": "number",
                "min": 3,
                "max": 365,
                "step": 1
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "cr_drop_percent",
            "metric_label": "Падение CR",
            "metric_unit": "%",
            "description": "Пороги критичности на основе процента падения конверсии (CR)",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичное падение CR",
                    "description": "Процент падения CR для критичного уровня",
                    "type": "number",
                    "min": 40,
                    "max": 100,
                    "step": 5,
                    "default": 70
                },
                "severity_high": {
                    "label": "Высокое падение CR",
                    "description": "Процент падения CR для высокого уровня",
                    "type": "number",
                    "min": 30,
                    "max": 90,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "Падение >= critical%"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical% > Падение >= high%"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "Падение < high%"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ кампаний с падением качества трафика через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с падением качества
        """
        # Получение параметров
        cr_drop_threshold = config.params.get("cr_drop_threshold", 40)
        traffic_stability = config.params.get("traffic_stability", 20)
        min_clicks = config.params.get("min_clicks", 500)
        sigma_threshold = config.params.get("sigma_threshold", 2.0)
        days = config.params.get("days", 7)

        # Получение настраиваемых порогов severity
        severity_critical_threshold = config.params.get("severity_critical", 70)
        severity_high_threshold = config.params.get("severity_high", 50)

        # Период для текущего и предыдущего периода
        # Текущий период: последние N дней (включая сегодня)
        current_period_start = datetime.now().date() - timedelta(days=days - 1)
        # Предыдущий период: N дней до текущего периода
        previous_period_start = current_period_start - timedelta(days=days)
        previous_period_end = current_period_start - timedelta(days=1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем дневную статистику за оба периода для анализа
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
                CampaignStatsDaily.date >= previous_period_start,
                CampaignStatsDaily.cost > 0  # только активные
            ).order_by(
                Campaign.internal_id,
                CampaignStatsDaily.date
            )

            results = query.all()

            # Группируем данные по кампаниям
            campaigns_data = {}
            for row in results:
                campaign_id = row.internal_id
                if campaign_id not in campaigns_data:
                    campaigns_data[campaign_id] = {
                        'binom_id': row.binom_id,
                        'name': row.current_name,
                        'group': row.group_name or "Без группы",
                        'current_period': {'clicks': 0, 'leads': 0, 'cost': 0, 'revenue': 0, 'days': []},
                        'previous_period': {'clicks': 0, 'leads': 0, 'cost': 0, 'revenue': 0, 'days': []},
                        'daily_cr': []  # для расчета стандартного отклонения
                    }

                # Распределяем данные по периодам
                date = row.date
                clicks = int(row.clicks)
                leads = int(row.leads)
                cost = float(row.cost)
                revenue = float(row.revenue)

                # Вычисляем CR для дня
                daily_cr = (leads / clicks * 100) if clicks > 0 else 0

                if date >= current_period_start:
                    # Текущий период
                    campaigns_data[campaign_id]['current_period']['clicks'] += clicks
                    campaigns_data[campaign_id]['current_period']['leads'] += leads
                    campaigns_data[campaign_id]['current_period']['cost'] += cost
                    campaigns_data[campaign_id]['current_period']['revenue'] += revenue
                    campaigns_data[campaign_id]['current_period']['days'].append(date)
                    campaigns_data[campaign_id]['daily_cr'].append(daily_cr)
                elif date >= previous_period_start and date <= previous_period_end:
                    # Предыдущий период
                    campaigns_data[campaign_id]['previous_period']['clicks'] += clicks
                    campaigns_data[campaign_id]['previous_period']['leads'] += leads
                    campaigns_data[campaign_id]['previous_period']['cost'] += cost
                    campaigns_data[campaign_id]['previous_period']['revenue'] += revenue
                    campaigns_data[campaign_id]['previous_period']['days'].append(date)
                    campaigns_data[campaign_id]['daily_cr'].append(daily_cr)

            # Анализируем кампании на предмет падения качества
            quality_crash_campaigns = []
            total_affected_clicks = 0

            for campaign_id, data in campaigns_data.items():
                current = data['current_period']
                previous = data['previous_period']

                # Фильтруем по минимальному количеству кликов в текущем периоде
                if current['clicks'] < min_clicks:
                    continue

                # Проверяем, что есть данные в обоих периодах
                if previous['clicks'] == 0 or current['clicks'] == 0:
                    continue

                # Вычисляем CR для обоих периодов
                current_cr = (current['leads'] / current['clicks'] * 100) if current['clicks'] > 0 else 0
                previous_cr = (previous['leads'] / previous['clicks'] * 100) if previous['clicks'] > 0 else 0

                # Проверяем падение CR > порога
                if previous_cr > 0:
                    cr_drop_percent = ((previous_cr - current_cr) / previous_cr * 100)
                    if cr_drop_percent < cr_drop_threshold:
                        continue  # падение недостаточное
                    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: current_cr должен быть меньше previous_cr
                    if current_cr >= previous_cr:
                        continue  # нет падения, возможен рост
                else:
                    continue  # нет данных за предыдущий период

                # Вычисляем стандартное отклонение (σ) для CR
                mean_cr = 0
                stdev_cr = 0
                deviation = 0

                if len(data['daily_cr']) >= 2:
                    try:
                        mean_cr = statistics.mean(data['daily_cr'])
                        stdev_cr = statistics.stdev(data['daily_cr'])

                        # СМЯГЧЕНИЕ: Sigma проверка только для умеренных падений
                        # Если падение > 50%, sigma не проверяем - это явно значимое изменение
                        if cr_drop_percent <= 50:
                            if stdev_cr > 0:
                                deviation = abs(current_cr - mean_cr) / stdev_cr
                                if deviation < sigma_threshold:
                                    continue  # недостаточное статистическое отклонение
                            # Если stdev = 0, проверяем только процент падения
                    except statistics.StatisticsError:
                        # Если не можем посчитать статистику, проверяем только падение CR
                        pass

                # Вычисляем метрики
                total_cost = current['cost']
                total_revenue = current['revenue']
                roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

                total_affected_clicks += current['clicks']

                # Определение критичности на основе степени падения CR
                if cr_drop_percent >= severity_critical_threshold:
                    severity = "critical"
                elif cr_drop_percent >= severity_high_threshold:
                    severity = "high"
                else:
                    severity = "medium"

                quality_crash_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data['binom_id'],
                    "name": data['name'],
                    "group": data['group'],
                    "current_cr": round(current_cr, 2),
                    "previous_cr": round(previous_cr, 2),
                    "cr_drop_percent": round(cr_drop_percent, 2),
                    "current_clicks": current['clicks'],
                    "previous_clicks": previous['clicks'],
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "avg_roi": round(roi, 2),
                    "mean_cr": round(mean_cr, 2),
                    "stdev_cr": round(stdev_cr, 2),
                    "sigma_deviation": round(deviation, 2),
                    "severity": severity
                })

            # Сортировка по проценту падения CR (самые сильные падения первыми)
            quality_crash_campaigns.sort(key=lambda x: x['cr_drop_percent'], reverse=True)

            return {
                "campaigns": quality_crash_campaigns,
                "summary": {
                    "total_found": len(quality_crash_campaigns),
                    "total_affected_clicks": total_affected_clicks,
                    "critical_count": sum(1 for c in quality_crash_campaigns if c['severity'] == 'critical'),
                    "high_count": sum(1 for c in quality_crash_campaigns if c['severity'] == 'high'),
                    "medium_count": sum(1 for c in quality_crash_campaigns if c['severity'] == 'medium')
                },
                "period_days": days,
                "thresholds": {
                    "cr_drop": cr_drop_threshold,
                    "traffic_stability": traffic_stability,
                    "min_clicks": min_clicks,
                    "sigma": sigma_threshold,
                    "severity_critical": severity_critical_threshold,
                    "severity_high": severity_high_threshold
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
        campaigns = raw_data["campaigns"][:10]  # Топ-10

        if not campaigns:
            return []

        return [
            {
                "id": "cr_comparison_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in campaigns],
                    "datasets": [
                        {
                            "label": "Предыдущий CR (%)",
                            "data": [c["previous_cr"] for c in campaigns],
                            "backgroundColor": "rgba(75, 192, 192, 0.5)",
                            "borderColor": "rgba(75, 192, 192, 1)",
                            "borderWidth": 1
                        },
                        {
                            "label": "Текущий CR (%)",
                            "data": [c["current_cr"] for c in campaigns],
                            "backgroundColor": "rgba(255, 99, 132, 0.5)",
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
                            "text": "Сравнение CR: Предыдущий vs Текущий период"
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True
                        }
                    }
                }
            },
            {
                "id": "cr_drop_chart",
                "type": "pie",
                "data": {
                    "labels": [c["name"][:25] for c in campaigns[:5]],
                    "datasets": [{
                        "data": [c["cr_drop_percent"] for c in campaigns[:5]],
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.8)",
                            "rgba(255, 159, 64, 0.8)",
                            "rgba(255, 205, 86, 0.8)",
                            "rgba(75, 192, 192, 0.8)",
                            "rgba(54, 162, 235, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Процент падения CR (Топ-5)"
                        }
                    }
                }
            }
        ]

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов.
        Возвращает один общий алерт с краткой сводкой вместо множества алертов.
        """
        summary = raw_data["summary"]
        campaigns = raw_data["campaigns"]
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        # Если есть кампании с падением качества, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            total_affected_clicks = summary["total_affected_clicks"]
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]

            # Получаем пороги для сообщения
            severity_critical_threshold = thresholds.get("severity_critical", 70)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: {total_found} кампаний с резким падением качества трафика"
                if critical_count > 1:
                    message += f" (из них {critical_count} с падением CR > {severity_critical_threshold}%)"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: {total_found} кампаний с падением качества трафика"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} кампаний с падением качества трафика"

            message += f"\nВсего затронуто кликов: {total_affected_clicks}"

            # Добавляем краткую информацию о топ-3
            top_3 = campaigns[:3]
            if top_3:
                message += "\n\nТоп-3 по падению CR:"
                for i, campaign in enumerate(top_3, 1):
                    message += f"\n{i}. {campaign['name']}: CR упал с {campaign['previous_cr']:.1f}% до {campaign['current_cr']:.1f}% (-{campaign['cr_drop_percent']:.1f}%)"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Срочно проверьте качество источников трафика. Рассмотрите остановку критических кампаний и проверку настроек таргетинга"
            else:
                recommended_action = "Проверьте настройки таргетинга и качество креативов. Возможно, аудитория выгорела или изменились условия на источнике"

            alerts.append({
                "type": "traffic_quality_crash_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "campaigns_count": total_found,
                "total_affected_clicks": total_affected_clicks,
                "critical_count": critical_count
            })

        return alerts
