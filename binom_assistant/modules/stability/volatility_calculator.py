"""
Модуль расчета волатильности метрик
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


class VolatilityCalculator(BaseModule):
    """
    Калькулятор волатильности метрик.

    Вычисляет стандартное отклонение и коэффициент вариации для ROI, CR и approve rate.
    Помогает оценить риски и предсказуемость кампании.

    Классификация волатильности:
    - Низкая: CV < 20%
    - Средняя: CV 20-50%
    - Высокая: CV > 50%
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="volatility_calculator",
            name="Колебания метрик",
            category="stability",
            description="Расчет волатильности ключевых метрик кампаний",
            detailed_description=(
                "Модуль вычисляет стандартное отклонение и коэффициент вариации для ROI, CR и approve rate. "
                "Помогает оценить риски и предсказуемость кампании за указанный период. "
                "Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой)."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["volatility", "risk", "stability", "roi", "cr"]
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
                "days": 14,  # Период анализа (14 дней)
                "min_spend": 1,  # Минимум $1 трат в день
                "min_days_with_data": 7,  # Минимум 7 дней с данными
                "severity_low": 20,  # Порог низкой волатильности (CV < 20%)
                "severity_medium": 50,  # Порог средней волатильности (CV < 50%)
                "severity_high": 150,  # Порог высокой волатильности (CV < 150%)
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
                "description": "Количество дней для расчета волатильности (включая сегодня)",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "min_spend": {
                "label": "Минимальный расход в день",
                "description": "Минимальный расход для учета дня в расчете ($)",
                "type": "number",
                "min": 0,
                "max": 10000,
                "step": 1
            },
            "min_days_with_data": {
                "label": "Минимум дней с данными",
                "description": "Минимальное количество дней с данными для расчета",
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
            "metric": "volatility",
            "metric_label": "Волатильность (CV)",
            "metric_unit": "%",
            "description": "Пороги критичности на основе коэффициента вариации. ВНИМАНИЕ: Высокая волатильность = плохо",
            "inverted": True,
            "thresholds": {
                "severity_low": {
                    "label": "Порог низкой волатильности",
                    "description": "Волатильность ниже этого значения считается низкой (хорошо)",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 20
                },
                "severity_medium": {
                    "label": "Порог средней волатильности",
                    "description": "Волатильность ниже этого значения (но выше низкой) считается средней",
                    "type": "number",
                    "min": 0,
                    "max": 200,
                    "step": 10,
                    "default": 50
                },
                "severity_high": {
                    "label": "Порог высокой волатильности",
                    "description": "Волатильность ниже этого значения (но выше средней) считается высокой",
                    "type": "number",
                    "min": 0,
                    "max": 300,
                    "step": 10,
                    "default": 150
                }
            },
            "levels": [
                {"value": "low", "label": "Низкая", "color": "#10b981", "condition": "CV < low"},
                {"value": "medium", "label": "Средняя", "color": "#fbbf24", "condition": "low <= CV < medium"},
                {"value": "high", "label": "Высокая", "color": "#ef4444", "condition": "medium <= CV < high"},
                {"value": "critical", "label": "Экстремальная", "color": "#dc2626", "condition": "CV >= high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ волатильности метрик через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о волатильности кампаний
        """
        # Получение параметров
        days = config.params.get("days", 14)
        min_spend = config.params.get("min_spend", 1)
        min_days_with_data = config.params.get("min_days_with_data", 7)

        # Получение настраиваемых порогов severity
        severity_low_threshold = config.params.get("severity_low", 20)
        severity_medium_threshold = config.params.get("severity_medium", 50)
        severity_high_threshold = config.params.get("severity_high", 150)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем дневную статистику кампаний за период
            query = session.query(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.a_leads
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost >= min_spend
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

                cost = float(row.cost)
                revenue = float(row.revenue)
                clicks = int(row.clicks)
                leads = int(row.leads)
                a_leads = int(row.a_leads)

                # Вычисляем дневные метрики
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                cr = (leads / clicks * 100) if clicks > 0 else 0
                approve_rate = (a_leads / leads * 100) if leads > 0 else 0

                campaigns_data[campaign_id].append({
                    'date': row.date,
                    'cost': cost,
                    'revenue': revenue,
                    'roi': roi,
                    'cr': cr,
                    'approve_rate': approve_rate,
                    'clicks': clicks,
                    'leads': leads,
                    'a_leads': a_leads
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
                        'group': campaign.group_name or "Без группы",
                        'is_cpl_mode': campaign.is_cpl_mode
                    }

            # Анализируем волатильность для каждой кампании
            low_volatility = []
            medium_volatility = []
            high_volatility = []
            extreme_volatility = []

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < min_days_with_data:
                    continue

                # Извлекаем метрики по дням
                roi_values = [d['roi'] for d in daily_data]
                cr_values = [d['cr'] for d in daily_data if d['clicks'] > 0]
                approve_rate_values = [d['approve_rate'] for d in daily_data if d['leads'] > 0]

                # Агрегированные показатели за весь период
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_clicks = sum(d['clicks'] for d in daily_data)
                total_leads = sum(d['leads'] for d in daily_data)
                total_a_leads = sum(d['a_leads'] for d in daily_data)

                # Средние метрики за период
                avg_roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
                avg_cr = (total_leads / total_clicks * 100) if total_clicks > 0 else 0
                avg_approve_rate = (total_a_leads / total_leads * 100) if total_leads > 0 else 0

                # Вычисляем стандартное отклонение (σ)
                roi_std = round(statistics.stdev(roi_values), 2) if len(roi_values) > 1 else 0
                cr_std = round(statistics.stdev(cr_values), 2) if len(cr_values) > 1 else 0
                approve_std = round(statistics.stdev(approve_rate_values), 2) if len(approve_rate_values) > 1 else 0

                # Вычисляем коэффициент вариации (CV = σ/μ * 100)
                # Ограничиваем CV максимум 500% для избежания экстремальных значений при малых средних
                MAX_CV = 500

                # ИСПРАВЛЕНО: Для ROI используем альтернативный метод при mean близком к нулю
                # CV не подходит для метрик с mean близким к 0 (ROI может быть отрицательным)
                # Вместо этого используем относительное стандартное отклонение от порога прибыльности (0%)
                if abs(avg_roi) > 5:  # Если средний ROI значительно отличается от 0
                    roi_cv = min(round((roi_std / abs(avg_roi) * 100), 2), MAX_CV)
                else:
                    # Альтернативная метрика для околонулевых средних:
                    # Нормализуем std_dev относительно порога значимости (50% ROI)
                    # Это показывает волатильность относительно ожидаемого диапазона прибыльности
                    roi_cv = min(round((roi_std / 50 * 100), 2), MAX_CV)

                if avg_cr > 0.1:
                    cr_cv = min(round((cr_std / avg_cr * 100), 2), MAX_CV)
                else:
                    cr_cv = 0

                if avg_approve_rate > 0.1:
                    approve_cv = min(round((approve_std / avg_approve_rate * 100), 2), MAX_CV)
                else:
                    approve_cv = 0

                # Общий индекс волатильности (средний CV)
                # Для CPL кампаний не учитываем approve rate
                campaign_info = campaigns_info.get(campaign_id, {'is_cpl_mode': False})
                is_cpl = campaign_info.get('is_cpl_mode', False)

                if is_cpl:
                    overall_volatility = round((roi_cv + cr_cv) / 2, 2)
                else:
                    overall_volatility = round((roi_cv + cr_cv + approve_cv) / 3, 2) if approve_cv > 0 else round((roi_cv + cr_cv) / 2, 2)

                # Классификация волатильности на основе настраиваемых порогов
                # Низкая: < severity_low (стабильная предсказуемая кампания)
                # Средняя: severity_low - severity_medium (умеренные колебания)
                # Высокая: severity_medium - severity_high (значительные колебания)
                # Экстремальная: > severity_high (непредсказуемая кампания)
                if overall_volatility < severity_low_threshold:
                    volatility_class = "low"
                    severity = "low"
                elif overall_volatility < severity_medium_threshold:
                    volatility_class = "medium"
                    severity = "medium"
                elif overall_volatility < severity_high_threshold:
                    volatility_class = "high"
                    severity = "high"
                else:
                    volatility_class = "extreme"
                    severity = "critical"

                # Формируем данные
                full_campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы",
                    'is_cpl_mode': False
                })

                campaign_volatility = {
                    "campaign_id": campaign_id,
                    "binom_id": full_campaign_info['binom_id'],
                    "name": full_campaign_info['name'],
                    "group": full_campaign_info['group'],

                    # Агрегированные метрики
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "avg_roi": round(avg_roi, 2),
                    "avg_cr": round(avg_cr, 2),
                    "avg_approve_rate": round(avg_approve_rate, 2),

                    # Волатильность ROI
                    "roi_std": roi_std,
                    "roi_cv": roi_cv,

                    # Волатильность CR
                    "cr_std": cr_std,
                    "cr_cv": cr_cv,

                    # Волатильность Approve Rate
                    "approve_std": approve_std,
                    "approve_cv": approve_cv,

                    # Общий индекс
                    "overall_volatility": overall_volatility,
                    "volatility_class": volatility_class,
                    "severity": severity,

                    # Дополнительные данные
                    "days_with_data": len(daily_data),
                    "is_cpl_mode": is_cpl
                }

                # Распределяем по категориям
                if volatility_class == "low":
                    low_volatility.append(campaign_volatility)
                elif volatility_class == "medium":
                    medium_volatility.append(campaign_volatility)
                elif volatility_class == "high":
                    high_volatility.append(campaign_volatility)
                else:  # extreme
                    extreme_volatility.append(campaign_volatility)

            # Сортировка
            low_volatility.sort(key=lambda x: x['overall_volatility'])
            medium_volatility.sort(key=lambda x: x['overall_volatility'])
            high_volatility.sort(key=lambda x: x['overall_volatility'])
            extreme_volatility.sort(key=lambda x: x['overall_volatility'], reverse=True)

            # Объединяем для общей таблицы (сначала наиболее стабильные)
            all_campaigns = low_volatility + medium_volatility + high_volatility + extreme_volatility

            return {
                "campaigns": all_campaigns,
                "low_volatility": low_volatility,
                "medium_volatility": medium_volatility,
                "high_volatility": high_volatility,
                "extreme_volatility": extreme_volatility,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_low": len(low_volatility),
                    "total_medium": len(medium_volatility),
                    "total_high": len(high_volatility),
                    "total_extreme": len(extreme_volatility),
                    "avg_volatility": round(
                        sum(c['overall_volatility'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "most_stable_volatility": round(low_volatility[0]['overall_volatility'], 2) if low_volatility else 0,
                    "most_volatile_volatility": round(extreme_volatility[0]['overall_volatility'], 2) if extreme_volatility else (round(high_volatility[0]['overall_volatility'], 2) if high_volatility else 0)
                },
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat(),
                    "days": days
                },
                "thresholds": {
                    "min_spend": min_spend,
                    "min_days_with_data": min_days_with_data,
                    "severity_low": severity_low_threshold,
                    "severity_medium": severity_medium_threshold,
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
        extreme_volatility = raw_data.get("extreme_volatility", [])[:10]
        high_volatility = raw_data["high_volatility"][:10]
        low_volatility = raw_data["low_volatility"][:10]

        charts = []

        # График: Экстремальная волатильность (>150%)
        if extreme_volatility:
            charts.append({
                "id": "extreme_volatility_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in extreme_volatility],
                    "datasets": [{
                        "label": "Индекс волатильности (%)",
                        "data": [c["overall_volatility"] for c in extreme_volatility],
                        "backgroundColor": "rgba(220, 38, 38, 0.5)",
                        "borderColor": "rgba(220, 38, 38, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-10 кампаний с экстремальной волатильностью (>150%)"
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

        # График: Высокая волатильность (50-150%)
        if high_volatility:
            charts.append({
                "id": "high_volatility_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in high_volatility],
                    "datasets": [{
                        "label": "Индекс волатильности (%)",
                        "data": [c["overall_volatility"] for c in high_volatility],
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
                            "text": "Топ-10 кампаний с высокой волатильностью (50-150%)"
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

        # График: Низкая волатильность (стабильные)
        if low_volatility:
            charts.append({
                "id": "low_volatility_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in low_volatility],
                    "datasets": [{
                        "label": "Индекс волатильности (%)",
                        "data": [c["overall_volatility"] for c in low_volatility],
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
                            "text": "Топ-10 наиболее стабильных кампаний"
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

        # Doughnut: Распределение по уровням волатильности
        summary = raw_data["summary"]
        if summary["total_analyzed"] > 0:
            charts.append({
                "id": "volatility_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Низкая (<20%)", "Средняя (20-50%)", "Высокая (50-150%)", "Экстремальная (>150%)"],
                    "datasets": [{
                        "data": [
                            summary["total_low"],
                            summary["total_medium"],
                            summary["total_high"],
                            summary.get("total_extreme", 0)
                        ],
                        "backgroundColor": [
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(251, 191, 36, 0.8)",
                            "rgba(239, 68, 68, 0.8)",
                            "rgba(220, 38, 38, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по уровням волатильности"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с высокой волатильностью.
        """
        alerts = []
        summary = raw_data["summary"]
        extreme_volatility = raw_data.get("extreme_volatility", [])
        high_volatility = raw_data["high_volatility"]
        thresholds = raw_data.get("thresholds", {})

        # Получаем порог для сообщения
        severity_high_threshold = thresholds.get("severity_high", 150)

        # Алерт о кампаниях с экстремальной волатильностью (> severity_high)
        if extreme_volatility:
            top_3 = extreme_volatility[:3]
            message = f"КРИТИЧНО: {len(extreme_volatility)} кампаний с экстремальной волатильностью (>{severity_high_threshold}%)"
            message += "\n\nТоп-3 наиболее непредсказуемых:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: волатильность {camp['overall_volatility']:.1f}%, ROI {camp['avg_roi']:.1f}%"

            alerts.append({
                "type": "extreme_volatility",
                "severity": "critical",
                "message": message,
                "recommended_action": "Экстремальная волатильность означает полную непредсказуемость результатов. Срочно остановите или снизьте бюджет до выяснения причин",
                "campaigns_count": len(extreme_volatility)
            })

        # Алерт о высокой доле нестабильных кампаний в портфеле
        if summary["total_analyzed"] > 0:
            high_volatility_pct = (summary["total_high"] / summary["total_analyzed"]) * 100
            if high_volatility_pct > 40:
                message = f"Высокая доля нестабильных кампаний в портфеле: {high_volatility_pct:.1f}%"
                message += f"\n\nНестабильных: {summary['total_high']}"
                message += f"\nСредняя волатильность: {summary['total_medium']}"
                message += f"\nСтабильных: {summary['total_low']}"

                alerts.append({
                    "type": "high_portfolio_volatility",
                    "severity": "medium",
                    "message": message,
                    "recommended_action": "Рассмотрите перераспределение бюджета в пользу более стабильных кампаний для снижения рисков",
                    "campaigns_count": summary["total_high"]
                })

        return alerts
