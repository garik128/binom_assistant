"""
Модуль анализа устойчивости результатов во времени
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict

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


class PerformanceStability(BaseModule):
    """
    Анализ устойчивости результатов во времени.

    Проверяет насколько устойчивы показатели кампании к внешним факторам
    (выходные, время суток). Выявляет зависимости от временных факторов.

    Логика анализа устойчивости:
    - Сравнение будни vs выходные
    - Анализ по часам суток (если есть данные)
    - Поиск сезонных паттернов
    - Устойчивость к единичным выбросам
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="performance_stability",
            name="Устойчивость результатов",
            category="stability",
            description="Анализ устойчивости результатов во времени",
            detailed_description=(
                "Модуль проверяет насколько устойчивы показатели кампании к внешним факторам "
                "(выходные, время суток). Выявляет зависимости от временных факторов и помогает "
                "определить кампании, которые стабильно работают в любых условиях."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["stability", "performance", "consistency", "temporal"]
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
                "days": 21,  # Период анализа (21 день для полных 3 недель)
                "min_spend": 1,  # Минимум $1 трат в день
                "min_days_with_data": 10,  # Минимум 10 дней с данными для анализа
                "weekday_weekend_diff_threshold": 30,  # Порог разницы будни/выходные (%)
                "stability_score_threshold": 70,  # Порог для высокой устойчивости
                "severity_high": 70,  # Порог высокой устойчивости (индекс >= 70)
                "severity_medium": 40,  # Порог средней устойчивости (индекс >= 40)
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
                "description": "Количество дней для анализа устойчивости (включая сегодня)",
                "type": "number",
                "min": 14,
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
                "description": "Минимальное количество дней с данными для анализа",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "weekday_weekend_diff_threshold": {
                "label": "Порог разницы будни/выходные (%)",
                "description": "Максимальная допустимая разница между буднями и выходными",
                "type": "number",
                "min": 10,
                "max": 100,
                "step": 5
            },
            "stability_score_threshold": {
                "label": "Порог высокой устойчивости",
                "description": "Минимальный индекс устойчивости для высокой категории",
                "type": "number",
                "min": 50,
                "max": 100,
                "step": 5
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "stability_score",
            "metric_label": "Индекс устойчивости",
            "metric_unit": "",
            "description": "Пороги критичности на основе индекса устойчивости (0-100). Высокий индекс = хорошо",
            "inverted": False,
            "thresholds": {
                "severity_high": {
                    "label": "Порог высокой устойчивости",
                    "description": "Индекс выше этого значения считается высоким (устойчив к внешним факторам)",
                    "type": "number",
                    "min": 50,
                    "max": 100,
                    "step": 5,
                    "default": 70
                },
                "severity_medium": {
                    "label": "Порог средней устойчивости",
                    "description": "Индекс выше этого значения (но ниже высокого) считается средним",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 40
                }
            },
            "levels": [
                {"value": "high", "label": "Высокая", "color": "#10b981", "condition": "score >= high", "severity": "low"},
                {"value": "medium", "label": "Средняя", "color": "#fbbf24", "condition": "medium <= score < high", "severity": "medium"},
                {"value": "low", "label": "Низкая", "color": "#ef4444", "condition": "score < medium", "severity": "high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ устойчивости результатов через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные об устойчивости кампаний
        """
        # Получение параметров
        days = config.params.get("days", 21)
        min_spend = config.params.get("min_spend", 1)
        min_days_with_data = config.params.get("min_days_with_data", 10)
        weekday_weekend_diff_threshold = config.params.get("weekday_weekend_diff_threshold", 30)
        stability_score_threshold = config.params.get("stability_score_threshold", 70)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", 70)
        severity_medium_threshold = config.params.get("severity_medium", 40)

        date_from = datetime.now().date() - timedelta(days=days - 1)  # Включаем текущий день

        # Работа с БД
        with get_db_session() as session:
            # Получаем дневную статистику кампаний за период
            query = session.query(
                CampaignStatsDaily.campaign_id,
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.clicks
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
                clicks = int(row.clicks or 0)
                profit = revenue - cost
                roi = round(((revenue - cost) / cost * 100), 2) if cost > 0 else 0

                # Определяем день недели (0 = понедельник, 6 = воскресенье)
                weekday = row.date.weekday()
                is_weekend = weekday >= 5  # Суббота (5) и Воскресенье (6)

                campaigns_data[campaign_id].append({
                    'date': row.date,
                    'weekday': weekday,
                    'is_weekend': is_weekend,
                    'cost': cost,
                    'revenue': revenue,
                    'profit': profit,
                    'roi': roi,
                    'clicks': clicks
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

            # Анализируем устойчивость для каждой кампании
            high_stability = []
            medium_stability = []
            low_stability = []

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < min_days_with_data:
                    continue

                # Разделяем на будни и выходные
                weekday_data = [d for d in daily_data if not d['is_weekend']]
                weekend_data = [d for d in daily_data if d['is_weekend']]

                # Рассчитываем средние метрики для будней
                weekday_avg_roi = 0
                weekday_avg_cost = 0
                weekday_avg_profit = 0
                if weekday_data:
                    weekday_avg_roi = round(sum(d['roi'] for d in weekday_data) / len(weekday_data), 2)
                    weekday_avg_cost = round(sum(d['cost'] for d in weekday_data) / len(weekday_data), 2)
                    weekday_avg_profit = round(sum(d['profit'] for d in weekday_data) / len(weekday_data), 2)

                # Рассчитываем средние метрики для выходных
                weekend_avg_roi = 0
                weekend_avg_cost = 0
                weekend_avg_profit = 0
                if weekend_data:
                    weekend_avg_roi = round(sum(d['roi'] for d in weekend_data) / len(weekend_data), 2)
                    weekend_avg_cost = round(sum(d['cost'] for d in weekend_data) / len(weekend_data), 2)
                    weekend_avg_profit = round(sum(d['profit'] for d in weekend_data) / len(weekend_data), 2)

                # Разница между буднями и выходными (%)
                weekday_weekend_roi_diff = 0
                if weekday_avg_roi != 0 and weekend_avg_roi != 0:
                    weekday_weekend_roi_diff = round(
                        abs(weekday_avg_roi - weekend_avg_roi) / abs(weekday_avg_roi) * 100, 2
                    )
                elif weekday_avg_roi != 0:
                    weekday_weekend_roi_diff = 100.0
                elif weekend_avg_roi != 0:
                    weekday_weekend_roi_diff = 100.0

                # Стандартное отклонение ROI (волатильность)
                roi_values = [d['roi'] for d in daily_data]
                avg_roi = sum(roi_values) / len(roi_values)
                variance = sum((x - avg_roi) ** 2 for x in roi_values) / len(roi_values)
                std_dev_roi = round(variance ** 0.5, 2)

                # Коэффициент вариации (CV) - нормализованная волатильность
                cv_roi = round((std_dev_roi / abs(avg_roi)) * 100, 2) if avg_roi != 0 else 0

                # Количество выбросов (значения выходящие за ±2σ)
                outliers_count = sum(1 for roi in roi_values if abs(roi - avg_roi) > 2 * std_dev_roi)
                outliers_pct = round((outliers_count / len(roi_values) * 100), 2)

                # Индекс устойчивости (0-100)
                # 40% - низкая разница будни/выходные (чем меньше, тем лучше)
                # 30% - низкая волатильность (чем меньше CV, тем лучше)
                # 30% - мало выбросов (чем меньше, тем лучше)

                # Балл за разницу будни/выходные (макс 40)
                score_weekday_weekend = max(0, 40 - (weekday_weekend_roi_diff / weekday_weekend_diff_threshold * 40))

                # Балл за волатильность (макс 30)
                # CV < 20% = отлично, CV > 100% = плохо
                score_volatility = max(0, 30 - (cv_roi / 100 * 30))

                # Балл за выбросы (макс 30)
                # < 5% выбросов = отлично, > 20% = плохо
                score_outliers = max(0, 30 - (outliers_pct / 20 * 30))

                stability_score = round(score_weekday_weekend + score_volatility + score_outliers, 2)

                # Классификация устойчивости на основе настраиваемых порогов
                if stability_score >= severity_high_threshold:
                    stability_class = "high"
                    severity = "low"  # Хорошая новость
                elif stability_score >= severity_medium_threshold:
                    stability_class = "medium"
                    severity = "medium"
                else:
                    stability_class = "low"
                    severity = "high"

                # Агрегированные показатели за весь период
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_profit = total_revenue - total_cost
                overall_roi = round(((total_revenue - total_cost) / total_cost * 100), 2) if total_cost > 0 else 0

                # Формируем данные
                full_campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы",
                    'is_cpl_mode': False
                })

                campaign_stability = {
                    "campaign_id": campaign_id,
                    "binom_id": full_campaign_info['binom_id'],
                    "name": full_campaign_info['name'],
                    "group": full_campaign_info['group'],

                    # Агрегированные метрики
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "total_profit": round(total_profit, 2),
                    "overall_roi": overall_roi,

                    # Метрики устойчивости
                    "stability_score": stability_score,
                    "stability_class": stability_class,

                    # Будни vs Выходные
                    "weekday_days": len(weekday_data),
                    "weekend_days": len(weekend_data),
                    "weekday_avg_roi": weekday_avg_roi,
                    "weekend_avg_roi": weekend_avg_roi,
                    "weekday_weekend_roi_diff": weekday_weekend_roi_diff,

                    # Волатильность
                    "std_dev_roi": std_dev_roi,
                    "cv_roi": cv_roi,

                    # Выбросы
                    "outliers_count": outliers_count,
                    "outliers_pct": outliers_pct,

                    # Дополнительные данные
                    "days_with_data": len(daily_data),
                    "severity": severity,
                    "is_cpl_mode": full_campaign_info.get('is_cpl_mode', False)
                }

                # Распределяем по категориям
                if stability_class == "high":
                    high_stability.append(campaign_stability)
                elif stability_class == "medium":
                    medium_stability.append(campaign_stability)
                else:
                    low_stability.append(campaign_stability)

            # Сортировка (по убыванию индекса устойчивости)
            high_stability.sort(key=lambda x: x['stability_score'], reverse=True)
            medium_stability.sort(key=lambda x: x['stability_score'], reverse=True)
            low_stability.sort(key=lambda x: x['stability_score'])

            # Объединяем для общей таблицы
            all_campaigns = high_stability + medium_stability + low_stability

            return {
                "campaigns": all_campaigns,
                "high_stability": high_stability,
                "medium_stability": medium_stability,
                "low_stability": low_stability,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_high": len(high_stability),
                    "total_medium": len(medium_stability),
                    "total_low": len(low_stability),
                    "avg_stability_score": round(
                        sum(c['stability_score'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "best_stability_score": round(high_stability[0]['stability_score'], 2) if high_stability else 0,
                    "worst_stability_score": round(low_stability[-1]['stability_score'], 2) if low_stability else 0,
                    "avg_weekday_weekend_diff": round(
                        sum(c['weekday_weekend_roi_diff'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "avg_cv_roi": round(
                        sum(c['cv_roi'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0
                },
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat(),
                    "days": days
                },
                "thresholds": {
                    "min_spend": min_spend,
                    "min_days_with_data": min_days_with_data,
                    "weekday_weekend_diff_threshold": weekday_weekend_diff_threshold,
                    "stability_score_threshold": stability_score_threshold,
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
        high_stability = raw_data["high_stability"][:10]
        low_stability = raw_data["low_stability"][:10]

        charts = []

        # График: Высокая устойчивость (топ-10)
        if high_stability:
            charts.append({
                "id": "high_stability_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in high_stability],
                    "datasets": [{
                        "label": "Индекс устойчивости",
                        "data": [c["stability_score"] for c in high_stability],
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
                            "text": "Топ-10 наиболее устойчивых кампаний"
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

        # График: Низкая устойчивость (худшие 10)
        if low_stability:
            charts.append({
                "id": "low_stability_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in low_stability],
                    "datasets": [{
                        "label": "Индекс устойчивости",
                        "data": [c["stability_score"] for c in low_stability],
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
                            "text": "Топ-10 наименее устойчивых кампаний"
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

        # Doughnut: Распределение по уровням устойчивости
        summary = raw_data["summary"]
        if summary["total_analyzed"] > 0:
            charts.append({
                "id": "stability_distribution",
                "type": "doughnut",
                "data": {
                    "labels": [
                        f"Высокая (≥{raw_data['thresholds']['stability_score_threshold']})",
                        f"Средняя (40-{raw_data['thresholds']['stability_score_threshold']})",
                        "Низкая (<40)"
                    ],
                    "datasets": [{
                        "data": [
                            summary["total_high"],
                            summary["total_medium"],
                            summary["total_low"]
                        ],
                        "backgroundColor": [
                            "rgba(16, 185, 129, 0.8)",
                            "rgba(251, 191, 36, 0.8)",
                            "rgba(239, 68, 68, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по уровням устойчивости"
                        }
                    }
                }
            })

        # График: Будни vs Выходные (топ-10 устойчивых)
        if high_stability:
            charts.append({
                "id": "weekday_weekend_comparison",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in high_stability],
                    "datasets": [
                        {
                            "label": "ROI Будни",
                            "data": [c["weekday_avg_roi"] for c in high_stability],
                            "backgroundColor": "rgba(59, 130, 246, 0.5)",
                            "borderColor": "rgba(59, 130, 246, 1)",
                            "borderWidth": 1
                        },
                        {
                            "label": "ROI Выходные",
                            "data": [c["weekend_avg_roi"] for c in high_stability],
                            "backgroundColor": "rgba(168, 85, 247, 0.5)",
                            "borderColor": "rgba(168, 85, 247, 1)",
                            "borderWidth": 1
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Сравнение ROI: Будни vs Выходные (топ-10)"
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с низкой устойчивостью.
        """
        alerts = []
        summary = raw_data["summary"]
        high_stability = raw_data["high_stability"]
        low_stability = raw_data["low_stability"]

        # Алерт о кампаниях с высокой устойчивостью
        if high_stability:
            top_3 = high_stability[:3]
            message = f"Найдено {len(high_stability)} устойчивых кампаний"
            message += "\n\nТоп-3 наиболее устойчивых:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['stability_score']:.1f}, разница будни/выходные {camp['weekday_weekend_roi_diff']:.1f}%"

            alerts.append({
                "type": "high_stability_opportunities",
                "severity": "low",
                "message": message,
                "recommended_action": "Эти кампании показывают стабильные результаты независимо от дня недели - подходят для масштабирования",
                "campaigns_count": len(high_stability)
            })

        # Алерт о кампаниях с низкой устойчивостью
        if low_stability:
            worst_3 = low_stability[:3]
            message = f"ВНИМАНИЕ: {len(low_stability)} кампаний с низкой устойчивостью результатов"
            message += "\n\nТоп-3 наименее устойчивых:"
            for i, camp in enumerate(worst_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['stability_score']:.1f}, волатильность {camp['cv_roi']:.1f}%"

            alerts.append({
                "type": "low_stability_warning",
                "severity": "high",
                "message": message,
                "recommended_action": "Результаты сильно зависят от внешних факторов - требуется оптимизация таргетинга или креативов",
                "campaigns_count": len(low_stability)
            })

        # Алерт о высокой доле неустойчивых кампаний
        if summary["total_analyzed"] > 0:
            low_stability_pct = (summary["total_low"] / summary["total_analyzed"]) * 100
            if low_stability_pct > 40:
                message = f"Высокая доля неустойчивых кампаний в портфеле: {low_stability_pct:.1f}%"
                message += f"\n\nНеустойчивых: {summary['total_low']}"
                message += f"\nСредней устойчивости: {summary['total_medium']}"
                message += f"\nУстойчивых: {summary['total_high']}"

                alerts.append({
                    "type": "portfolio_instability",
                    "severity": "medium",
                    "message": message,
                    "recommended_action": "Сфокусируйтесь на более устойчивых кампаниях для снижения зависимости от внешних факторов",
                    "campaigns_count": summary["total_low"]
                })

        # Алерт о сильной зависимости от дня недели
        high_weekday_dependency = [
            c for c in raw_data["campaigns"]
            if c["weekday_weekend_roi_diff"] > raw_data["thresholds"]["weekday_weekend_diff_threshold"]
        ]
        if len(high_weekday_dependency) > 5:
            top_3_dep = sorted(high_weekday_dependency, key=lambda x: x["weekday_weekend_roi_diff"], reverse=True)[:3]
            message = f"Обнаружено {len(high_weekday_dependency)} кампаний с сильной зависимостью от дня недели"
            message += "\n\nТоп-3 самых зависимых:"
            for i, camp in enumerate(top_3_dep, 1):
                message += f"\n{i}. {camp['name']}: разница {camp['weekday_weekend_roi_diff']:.1f}%"

            alerts.append({
                "type": "weekday_dependency",
                "severity": "medium",
                "message": message,
                "recommended_action": "Рассмотрите раздельные стратегии для будней и выходных (разные ставки или креативы)",
                "campaigns_count": len(high_weekday_dependency)
            })

        return alerts
