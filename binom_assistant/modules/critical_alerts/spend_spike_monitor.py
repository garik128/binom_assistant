"""
Модуль мониторинга всплесков расходов
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


class SpendSpikeMonitor(BaseModule):
    """
    Детектор аномальных всплесков расходов.

    Находит кампании с неожиданными скачками в расходах, которые могут указывать
    на технические проблемы или изменения в источнике.

    Критерии:
    - Расход за последние 24ч > среднего за 7 дней + 3σ
    - Абсолютное увеличение > $20 (настраивается)
    - Без соответствующего роста конверсий (CR не вырос пропорционально)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="spend_spike_monitor",
            name="Всплеск расходов",
            category="critical_alerts",
            description="Детектирует аномальные всплески расходов выше нормы",
            detailed_description="Обнаруживает неожиданные скачки в расходах используя статистический анализ (среднее + 2σ). Защищает от внезапного опустошения бюджета при технических проблемах или изменениях в источнике.",
            version="1.0.2",
            author="Binom Assistant",
            priority="critical",
            tags=["spend", "spike", "anomaly", "critical"]
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
                "base_days": 7,  # базовый период для расчета среднего и σ
                "spike_threshold": 2,  # минимальное абсолютное увеличение в $ (оптимально для малых и средних кампаний)
                "sigma_multiplier": 2,  # множитель для стандартного отклонения (2σ = 95.4% нормального распределения)
                "min_base_spend": 1,  # минимальный средний расход в базовом периоде
                "cr_growth_threshold": 40,  # минимальный рост CR (%) для игнорирования всплеска (если CR вырос пропорционально - это масштабирование)
                "severity_critical": 2.0,  # кратность превышения порога для critical severity
                "severity_high": 1.5  # кратность превышения порога для high severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает метаданные параметров для UI.

        Returns:
            Dict с описаниями параметров
        """
        return {
            "base_days": {
                "label": "Базовый период (дней)",
                "description": "Количество дней для расчета среднего расхода и стандартного отклонения",
                "type": "number",
                "min": 3,
                "max": 365,
                "step": 1
            },
            "spike_threshold": {
                "label": "Порог всплеска (кратность)",
                "description": "Минимальное увеличение расхода по отношению к среднему (например, 2 = в 2 раза)",
                "type": "number",
                "min": 1.5,
                "max": 10,
                "step": 0.5
            },
            "sigma_multiplier": {
                "label": "Множитель сигма",
                "description": "Множитель для стандартного отклонения (2σ = 95.4%, 3σ = 99.7%)",
                "type": "number",
                "min": 1,
                "max": 5,
                "step": 0.5
            },
            "min_base_spend": {
                "label": "Минимальный средний расход ($)",
                "description": "Минимальный средний расход в базовом периоде для анализа",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "step": 0.5
            },
            "cr_growth_threshold": {
                "label": "Порог роста CR (%)",
                "description": "Минимальный рост CR для игнорирования всплеска (если CR вырос - это масштабирование)",
                "type": "number",
                "min": 10,
                "max": 100,
                "step": 5
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "spike_ratio",
            "metric_label": "Кратность всплеска",
            "metric_unit": "x",
            "description": "Пороги критичности на основе превышения статистического порога расходов",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичная кратность",
                    "description": "Превышение статистического порога для критичного уровня (кратность)",
                    "type": "number",
                    "min": 1.2,
                    "max": 5,
                    "step": 0.1,
                    "default": 2.0
                },
                "severity_high": {
                    "label": "Высокая кратность",
                    "description": "Превышение статистического порога для высокого уровня (кратность)",
                    "type": "number",
                    "min": 1.1,
                    "max": 3,
                    "step": 0.1,
                    "default": 1.5
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "Кратность >= critical"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical > Кратность >= high"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "Кратность < high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ всплесков расходов через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с всплесками расходов
        """
        # Получение параметров
        base_days = config.params.get("base_days", 7)
        spike_threshold = config.params.get("spike_threshold", 2)
        sigma_multiplier = config.params.get("sigma_multiplier", 2)
        min_base_spend = config.params.get("min_base_spend", 1)
        cr_growth_threshold = config.params.get("cr_growth_threshold", 40)

        # Получение настраиваемых порогов severity
        severity_critical_threshold = config.params.get("severity_critical", 2.0)
        severity_high_threshold = config.params.get("severity_high", 1.5)

        # Период: base_days (например 7) + 1 последний день для анализа
        # Анализируем ВЧЕРАШНИЙ день (т.к. сегодняшние данные могут быть неполными)
        total_days = base_days + 1
        last_day = datetime.now().date() - timedelta(days=1)  # вчера - день для проверки всплеска
        date_from = last_day - timedelta(days=total_days - 1)  # начало периода

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с их дневной статистикой за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.cr
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost > 0  # только с расходами
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
                        'group': row.group_name,
                        'daily_data': []
                    }

                campaigns_data[campaign_id]['daily_data'].append({
                    'date': row.date,
                    'cost': float(row.cost),
                    'revenue': float(row.revenue) if row.revenue else 0,
                    'clicks': int(row.clicks) if row.clicks else 0,
                    'leads': int(row.leads) if row.leads else 0,
                    'cr': float(row.cr) if row.cr else 0
                })

            # Анализируем каждую кампанию на всплески
            spike_campaigns = []
            total_extra_spend = 0

            for campaign_id, data in campaigns_data.items():
                daily_data = data['daily_data']

                # Разделяем на базовый период и последний день
                base_period_data = [d for d in daily_data if d['date'] < last_day]
                last_day_data = [d for d in daily_data if d['date'] == last_day]

                # Проверяем что есть данные для анализа
                if not base_period_data or not last_day_data:
                    continue

                # Базовый период: должен быть минимум base_days дней для статистики
                if len(base_period_data) < base_days:
                    continue

                # Расходы в базовом периоде
                base_costs = [d['cost'] for d in base_period_data]
                base_crs = [d['cr'] for d in base_period_data if d['cr'] > 0]

                # Расход за последний день
                last_day_cost = last_day_data[0]['cost']
                last_day_cr = last_day_data[0]['cr']
                last_day_clicks = last_day_data[0]['clicks']
                last_day_leads = last_day_data[0]['leads']

                # Статистика базового периода
                mean_cost = statistics.mean(base_costs)

                # Проверка минимального среднего расхода
                if mean_cost < min_base_spend:
                    continue

                # Стандартное отклонение (если всего 1-2 дня, используем упрощенную формулу)
                if len(base_costs) > 1:
                    stdev_cost = statistics.stdev(base_costs)
                else:
                    stdev_cost = 0

                mean_cr = statistics.mean(base_crs) if base_crs else 0

                # Пороговое значение для всплеска
                spike_limit = mean_cost + (sigma_multiplier * stdev_cost)

                # Абсолютное увеличение
                absolute_increase = last_day_cost - mean_cost

                # Вычисляем кратность превышения
                cost_ratio = last_day_cost / mean_cost if mean_cost > 0 else 0

                # ПРОВЕРКА: Расход превышает статистический порог ИЛИ вырос в N раз
                # Используется OR логика: достаточно одного условия для детекции
                statistical_spike = last_day_cost > spike_limit
                ratio_spike = cost_ratio >= spike_threshold

                if not (statistical_spike or ratio_spike):
                    continue

                # ПРОВЕРКА 3: Нет соответствующего роста конверсий
                # Если CR вырос пропорционально или больше, это нормальное масштабирование
                if mean_cr > 0:
                    cr_change_percent = ((last_day_cr - mean_cr) / mean_cr) * 100
                    # Если CR вырос больше чем на cr_growth_threshold%, считаем это нормальным ростом
                    if cr_change_percent >= cr_growth_threshold:
                        continue
                else:
                    # Если раньше CR не было, но теперь есть - это хорошо
                    if last_day_cr > 0:
                        continue

                # Всплеск обнаружен!
                total_extra_spend += absolute_increase

                # Определение критичности на основе превышения порога
                spike_ratio = last_day_cost / spike_limit if spike_limit > 0 else 1

                if spike_ratio >= severity_critical_threshold:
                    severity = "critical"
                elif spike_ratio >= severity_high_threshold:
                    severity = "high"
                else:
                    severity = "medium"

                # Агрегированные метрики за весь период для таблицы
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)

                # Расчет ROI
                avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

                spike_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data['binom_id'],
                    "name": data['name'],
                    "group": data['group'] or "Без группы",
                    "last_day_cost": last_day_cost,
                    "mean_cost": round(mean_cost, 2),
                    "stdev_cost": round(stdev_cost, 2),
                    "spike_limit": round(spike_limit, 2),
                    "absolute_increase": round(absolute_increase, 2),
                    "spike_ratio": round(spike_ratio, 2),
                    "last_day_cr": round(last_day_cr, 2),
                    "mean_cr": round(mean_cr, 2),
                    "severity": severity,
                    # Обязательные поля для таблицы
                    "total_cost": total_cost,
                    "total_revenue": total_revenue,
                    "avg_roi": round(avg_roi, 2),
                    "total_clicks": total_clicks,
                    "total_leads": total_leads
                })

            # Сортировка по абсолютному увеличению (наибольшие всплески первыми)
            spike_campaigns.sort(key=lambda x: x['absolute_increase'], reverse=True)

            return {
                "campaigns": spike_campaigns,
                "summary": {
                    "total_found": len(spike_campaigns),
                    "total_extra_spend": round(total_extra_spend, 2),
                    "critical_count": sum(1 for c in spike_campaigns if c['severity'] == 'critical'),
                    "high_count": sum(1 for c in spike_campaigns if c['severity'] == 'high'),
                    "medium_count": sum(1 for c in spike_campaigns if c['severity'] == 'medium'),
                    "avg_spike_ratio": round(
                        statistics.mean([c['spike_ratio'] for c in spike_campaigns])
                        if spike_campaigns else 0, 2
                    )
                },
                "period_days": total_days,
                "thresholds": {
                    "base_days": base_days,
                    "spike_threshold": spike_threshold,
                    "sigma_multiplier": sigma_multiplier,
                    "min_base_spend": min_base_spend,
                    "cr_growth_threshold": cr_growth_threshold,
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
                "id": "spike_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in campaigns],
                    "datasets": [
                        {
                            "label": "Последний день ($)",
                            "data": [c["last_day_cost"] for c in campaigns],
                            "backgroundColor": "rgba(255, 99, 132, 0.5)",
                            "borderColor": "rgba(255, 99, 132, 1)",
                            "borderWidth": 1
                        },
                        {
                            "label": "Среднее за 7 дней ($)",
                            "data": [c["mean_cost"] for c in campaigns],
                            "backgroundColor": "rgba(75, 192, 192, 0.5)",
                            "borderColor": "rgba(75, 192, 192, 1)",
                            "borderWidth": 1
                        },
                        {
                            "label": "Порог (среднее + 3σ)",
                            "data": [c["spike_limit"] for c in campaigns],
                            "backgroundColor": "rgba(255, 206, 86, 0.5)",
                            "borderColor": "rgba(255, 206, 86, 1)",
                            "borderWidth": 1
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Сравнение расходов: последний день vs средние"
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "title": {
                                "display": True,
                                "text": "Расход ($)"
                            }
                        }
                    }
                }
            },
            {
                "id": "increase_chart",
                "type": "pie",
                "data": {
                    "labels": [c["name"][:25] for c in campaigns[:5]],
                    "datasets": [{
                        "data": [c["absolute_increase"] for c in campaigns[:5]],
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
                            "text": "Распределение излишних расходов (Топ-5)"
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

        # Если есть кампании с всплесками, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            total_extra_spend = summary["total_extra_spend"]
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]
            avg_spike_ratio = summary["avg_spike_ratio"]

            # Получаем пороги для сообщения
            severity_critical_threshold = thresholds.get("severity_critical", 2.0)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: {total_found} кампаний с аномальными всплесками расходов, излишне потрачено: ${total_extra_spend:.2f}"
                if critical_count > 1:
                    message += f" (из них {critical_count} с превышением >{severity_critical_threshold}x)"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: {total_found} кампаний с всплесками расходов, излишне потрачено: ${total_extra_spend:.2f}"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} кампаний с всплесками расходов, излишне потрачено: ${total_extra_spend:.2f}"

            message += f"\nСреднее превышение порога: {avg_spike_ratio:.1f}x"

            # Добавляем краткую информацию о топ-3
            top_3 = campaigns[:3]
            if top_3:
                message += "\n\nТоп-3 по всплеску:"
                for i, campaign in enumerate(top_3, 1):
                    message += f"\n{i}. {campaign['name']}: +${campaign['absolute_increase']:.2f} (превышение {campaign['spike_ratio']:.1f}x)"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Срочно проверьте настройки источников и лимиты расходов. Возможны технические проблемы или изменения в тарифах"
            else:
                recommended_action = "Проверьте источники трафика и убедитесь что увеличение расходов запланировано"

            alerts.append({
                "type": "spend_spike_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "campaigns_count": total_found,
                "total_extra_spend": total_extra_spend,
                "critical_count": critical_count,
                "avg_spike_ratio": avg_spike_ratio
            })

        return alerts
