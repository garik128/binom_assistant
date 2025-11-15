"""
Модуль оценки надежности кампаний
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


class ReliabilityIndex(BaseModule):
    """
    Комплексная оценка надежности для масштабирования.

    Интегральный показатель, учитывающий историю, стабильность и объемы.
    Определяет кампании, готовые к увеличению бюджета.

    Логика расчета надежности:
    - Возраст кампании (вес 20%)
    - Стабильность ROI (вес 30%)
    - Объем данных/лидов (вес 25%)
    - Consistency score (вес 25%)
    - Финальный индекс 0-100
    - Минимальный расход > $1/день
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="reliability_index",
            name="Надёжность",
            category="stability",
            description="Комплексная оценка надежности для масштабирования",
            detailed_description=(
                "Модуль рассчитывает интегральный показатель надежности кампании, учитывающий возраст, "
                "стабильность ROI, объем данных и консистентность прибыли. Помогает определить кампании, "
                "готовые к увеличению бюджета без риска. "
                "Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой)."
            ),
            version="1.0.1",
            author="Binom Assistant",
            priority="medium",
            tags=["reliability", "stability", "scaling", "index"]
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
                "days": 30,  # Период анализа (30 дней)
                "min_spend": 1,  # Минимум $1 трат в день
                "min_days_with_data": 14,  # Минимум 14 дней с данными
                "reliability_threshold": 70,  # Порог для высокой надежности
                "min_leads": 10,  # Минимум лидов для учета объема данных
                "severity_high": 70,  # Порог высокой надежности (индекс >= 70)
                "severity_medium": 50,  # Порог средней надежности (индекс >= 50)
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
                "description": "Количество дней для расчета надежности (включая сегодня)",
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
                "description": "Минимальное количество дней с данными для расчета",
                "type": "number",
                "min": 7,
                "max": 365,
                "step": 1
            },
            "reliability_threshold": {
                "label": "Порог высокой надежности",
                "description": "Минимальный индекс надежности для высокого класса (0-100)",
                "type": "number",
                "min": 50,
                "max": 100,
                "step": 5
            },
            "min_leads": {
                "label": "Минимум лидов",
                "description": "Минимальное количество лидов для учета объема данных",
                "type": "number",
                "min": 1,
                "max": 1000,
                "step": 1
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "reliability_index",
            "metric_label": "Индекс надежности",
            "metric_unit": "",
            "description": "Пороги критичности на основе индекса надежности (0-100). Высокий индекс = хорошо",
            "inverted": False,
            "thresholds": {
                "severity_high": {
                    "label": "Порог высокой надежности",
                    "description": "Индекс выше этого значения считается высоким (готов к масштабированию)",
                    "type": "number",
                    "min": 50,
                    "max": 100,
                    "step": 5,
                    "default": 70
                },
                "severity_medium": {
                    "label": "Порог средней надежности",
                    "description": "Индекс выше этого значения (но ниже высокого) считается средним",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "high", "label": "Высокая", "color": "#10b981", "condition": "index >= high", "severity": "low"},
                {"value": "medium", "label": "Средняя", "color": "#fbbf24", "condition": "medium <= index < high", "severity": "medium"},
                {"value": "low", "label": "Низкая", "color": "#ef4444", "condition": "index < medium", "severity": "high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ надежности кампаний через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о надежности кампаний
        """
        # Получение параметров
        days = config.params.get("days", 30)
        min_spend = config.params.get("min_spend", 1)
        min_days_with_data = config.params.get("min_days_with_data", 14)
        reliability_threshold = config.params.get("reliability_threshold", 70)
        min_leads = config.params.get("min_leads", 10)

        # Получение настраиваемых порогов severity
        severity_high_threshold = config.params.get("severity_high", 70)
        severity_medium_threshold = config.params.get("severity_medium", 50)

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
                    campaigns_data[campaign_id] = {
                        'first_date': row.date,
                        'last_date': row.date,
                        'daily_stats': []
                    }

                cost = float(row.cost)
                revenue = float(row.revenue)
                profit = revenue - cost
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0

                campaigns_data[campaign_id]['daily_stats'].append({
                    'date': row.date,
                    'cost': cost,
                    'revenue': revenue,
                    'profit': profit,
                    'roi': roi,
                    'clicks': int(row.clicks) if row.clicks else 0,
                    'leads': int(row.leads) if row.leads else 0,
                    'a_leads': int(row.a_leads) if row.a_leads else 0,
                    'is_profitable': profit > 0
                })

                # Обновляем даты
                if row.date < campaigns_data[campaign_id]['first_date']:
                    campaigns_data[campaign_id]['first_date'] = row.date
                if row.date > campaigns_data[campaign_id]['last_date']:
                    campaigns_data[campaign_id]['last_date'] = row.date

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
                        'is_cpl_mode': campaign.is_cpl_mode,
                        'created_at': campaign.created_at
                    }

            # Анализируем надежность для каждой кампании
            high_reliability = []
            medium_reliability = []
            low_reliability = []

            for campaign_id, camp_data in campaigns_data.items():
                daily_stats = camp_data['daily_stats']

                # Пропускаем если недостаточно данных
                if len(daily_stats) < min_days_with_data:
                    continue

                # === 1. Возраст кампании (вес 20%) ===
                campaign_age_days = (datetime.now().date() - camp_data['first_date']).days
                # Чем старше, тем лучше (макс балл при 60+ днях)
                age_score = min(campaign_age_days / 60 * 100, 100)

                # === 2. Стабильность ROI (вес 30%) ===
                # ИСПРАВЛЕНО: Правильный расчет коэффициента вариации ROI
                # CV = (std_dev / mean) * 100, но для ROI нужна особая обработка
                roi_values = [d['roi'] for d in daily_stats]

                if len(roi_values) > 1:
                    mean_roi = statistics.mean(roi_values)
                    std_roi = statistics.stdev(roi_values)

                    # Для ROI используем альтернативный подход при mean близком к 0
                    if abs(mean_roi) > 5:  # Если средний ROI значительно отличается от 0
                        cv_roi = (std_roi / abs(mean_roi)) * 100
                    else:
                        # Для околонулевых средних используем нормализацию относительно порога (50%)
                        cv_roi = (std_roi / 50) * 100
                else:
                    cv_roi = 100  # Недостаточно данных = максимальная неопределенность

                # Чем меньше вариация, тем выше балл (CV < 20% = 100 баллов, > 100% = 0 баллов)
                stability_score = max(0, 100 - cv_roi)

                # === 3. Объем данных/лидов (вес 25%) ===
                total_clicks = sum(d['clicks'] for d in daily_stats)
                total_leads_all = sum(d['leads'] for d in daily_stats)
                total_leads = sum(d['a_leads'] for d in daily_stats)

                # Учитываем как клики, так и лиды
                clicks_score = min(total_clicks / 1000 * 100, 100)  # Макс балл при 1000+ кликов
                leads_score = min(total_leads / min_leads * 100, 100)  # Макс балл при min_leads+ лидов
                volume_score = (clicks_score + leads_score) / 2

                # === 4. Consistency score (вес 25%) ===
                # Рассчитываем как в consistency_scorer
                profitable_days = sum(1 for d in daily_stats if d['is_profitable'])
                unprofitable_days = len(daily_stats) - profitable_days
                profitable_days_pct = (profitable_days / len(daily_stats) * 100) if daily_stats else 0

                if unprofitable_days > 0:
                    profit_loss_ratio = profitable_days / unprofitable_days
                else:
                    profit_loss_ratio = float(profitable_days)

                # Расчет максимальной просадки
                cumulative_profit = 0
                peak_profit = 0
                max_drawdown = 0

                for d in daily_stats:
                    cumulative_profit += d['profit']
                    if cumulative_profit > peak_profit:
                        peak_profit = cumulative_profit
                    drawdown = peak_profit - cumulative_profit
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown

                if peak_profit > 0:
                    max_drawdown_pct = (max_drawdown / peak_profit * 100)
                else:
                    max_drawdown_pct = 0

                # Индекс консистентности (0-100)
                score_profitable_days = profitable_days_pct * 0.5
                score_ratio = min(profit_loss_ratio / 10 * 30, 30)
                score_drawdown = max(0, (100 - max_drawdown_pct)) * 0.2
                consistency_score = score_profitable_days + score_ratio + score_drawdown

                # === ФИНАЛЬНЫЙ ИНДЕКС НАДЕЖНОСТИ (0-100) ===
                reliability_index = round(
                    age_score * 0.20 +
                    stability_score * 0.30 +
                    volume_score * 0.25 +
                    consistency_score * 0.25,
                    2
                )

                # Классификация надежности на основе настраиваемых порогов
                if reliability_index >= severity_high_threshold:
                    reliability_class = "high"
                    severity = "low"  # Хорошая новость
                elif reliability_index >= severity_medium_threshold:
                    reliability_class = "medium"
                    severity = "medium"
                else:
                    reliability_class = "low"
                    severity = "high"

                # Агрегированные показатели
                total_cost = sum(d['cost'] for d in daily_stats)
                total_revenue = sum(d['revenue'] for d in daily_stats)
                total_profit = total_revenue - total_cost
                avg_roi = round(((total_revenue - total_cost) / total_cost * 100), 2) if total_cost > 0 else 0

                # Формируем данные
                full_campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы",
                    'is_cpl_mode': False
                })

                campaign_reliability = {
                    "campaign_id": campaign_id,
                    "binom_id": full_campaign_info['binom_id'],
                    "name": full_campaign_info['name'],
                    "group": full_campaign_info['group'],

                    # Агрегированные метрики
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "total_profit": round(total_profit, 2),
                    "avg_roi": avg_roi,

                    # Индекс надежности и его компоненты
                    "reliability_index": reliability_index,
                    "reliability_class": reliability_class,
                    "age_score": round(age_score, 2),
                    "stability_score": round(stability_score, 2),
                    "volume_score": round(volume_score, 2),
                    "consistency_score": round(consistency_score, 2),

                    # Дополнительные данные
                    "campaign_age_days": campaign_age_days,
                    "cv_roi": round(cv_roi, 2),
                    "total_clicks": total_clicks,
                    "total_leads_all": total_leads_all,
                    "total_leads": total_leads,
                    "profitable_days_pct": round(profitable_days_pct, 2),
                    "days_with_data": len(daily_stats),
                    "severity": severity,
                    "is_cpl_mode": full_campaign_info.get('is_cpl_mode', False)
                }

                # Распределяем по категориям
                if reliability_class == "high":
                    high_reliability.append(campaign_reliability)
                elif reliability_class == "medium":
                    medium_reliability.append(campaign_reliability)
                else:
                    low_reliability.append(campaign_reliability)

            # Сортировка (по убыванию индекса надежности)
            high_reliability.sort(key=lambda x: x['reliability_index'], reverse=True)
            medium_reliability.sort(key=lambda x: x['reliability_index'], reverse=True)
            low_reliability.sort(key=lambda x: x['reliability_index'])

            # Объединяем для общей таблицы
            all_campaigns = high_reliability + medium_reliability + low_reliability

            return {
                "campaigns": all_campaigns,
                "high_reliability": high_reliability,
                "medium_reliability": medium_reliability,
                "low_reliability": low_reliability,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_high": len(high_reliability),
                    "total_medium": len(medium_reliability),
                    "total_low": len(low_reliability),
                    "avg_reliability_index": round(
                        sum(c['reliability_index'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "best_reliability_index": round(all_campaigns[0]['reliability_index'], 2) if all_campaigns else 0,
                    "worst_reliability_index": round(all_campaigns[-1]['reliability_index'], 2) if all_campaigns else 0,
                    "avg_campaign_age": round(
                        sum(c['campaign_age_days'] for c in all_campaigns) / len(all_campaigns), 2
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
                    "reliability_threshold": reliability_threshold,
                    "min_leads": min_leads,
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
        high_reliability = raw_data["high_reliability"][:10]
        low_reliability = raw_data["low_reliability"][:10]

        charts = []

        # График: Высокая надежность (топ-10)
        if high_reliability:
            charts.append({
                "id": "high_reliability_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in high_reliability],
                    "datasets": [{
                        "label": "Индекс надежности",
                        "data": [c["reliability_index"] for c in high_reliability],
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
                            "text": "Топ-10 наиболее надежных кампаний"
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

        # График: Компоненты индекса надежности (средние значения)
        summary = raw_data["summary"]
        if summary["total_analyzed"] > 0:
            all_campaigns = raw_data["campaigns"]
            avg_age = sum(c['age_score'] for c in all_campaigns) / len(all_campaigns)
            avg_stability = sum(c['stability_score'] for c in all_campaigns) / len(all_campaigns)
            avg_volume = sum(c['volume_score'] for c in all_campaigns) / len(all_campaigns)
            avg_consistency = sum(c['consistency_score'] for c in all_campaigns) / len(all_campaigns)

            charts.append({
                "id": "reliability_components_chart",
                "type": "radar",
                "data": {
                    "labels": ["Возраст кампании", "Стабильность ROI", "Объем данных", "Консистентность"],
                    "datasets": [{
                        "label": "Средние значения компонентов",
                        "data": [
                            round(avg_age, 2),
                            round(avg_stability, 2),
                            round(avg_volume, 2),
                            round(avg_consistency, 2)
                        ],
                        "backgroundColor": "rgba(59, 130, 246, 0.2)",
                        "borderColor": "rgba(59, 130, 246, 1)",
                        "borderWidth": 2
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Средние значения компонентов индекса надежности"
                        }
                    },
                    "scales": {
                        "r": {
                            "beginAtZero": True,
                            "max": 100
                        }
                    }
                }
            })

        # Doughnut: Распределение по уровням надежности
        if summary["total_analyzed"] > 0:
            charts.append({
                "id": "reliability_distribution",
                "type": "doughnut",
                "data": {
                    "labels": [
                        f"Высокая (≥{raw_data['thresholds']['reliability_threshold']})",
                        f"Средняя (50-{raw_data['thresholds']['reliability_threshold']})",
                        "Низкая (<50)"
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
                            "text": "Распределение по уровням надежности"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с высокой и низкой надежностью.
        """
        alerts = []
        summary = raw_data["summary"]
        high_reliability = raw_data["high_reliability"]
        low_reliability = raw_data["low_reliability"]

        # Алерт о кампаниях с высокой надежностью (готовы к масштабированию)
        if high_reliability:
            top_3 = high_reliability[:3]
            message = f"Найдено {len(high_reliability)} надежных кампаний готовых к масштабированию"
            message += "\n\nТоп-3 наиболее надежных:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['reliability_index']:.1f}, возраст {camp['campaign_age_days']} дней"

            alerts.append({
                "type": "high_reliability_scaling",
                "severity": "low",
                "message": message,
                "recommended_action": "Эти кампании показывают высокую надежность и подходят для увеличения бюджета",
                "campaigns_count": len(high_reliability)
            })

        # Алерт о кампаниях с низкой надежностью
        if low_reliability:
            worst_3 = low_reliability[:3]
            message = f"ВНИМАНИЕ: {len(low_reliability)} кампаний с низкой надежностью"
            message += "\n\nТоп-3 наименее надежных:"
            for i, camp in enumerate(worst_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['reliability_index']:.1f}"

            alerts.append({
                "type": "low_reliability_warning",
                "severity": "high",
                "message": message,
                "recommended_action": "Не рекомендуется увеличивать бюджет этих кампаний до улучшения показателей",
                "campaigns_count": len(low_reliability)
            })

        # Алерт о молодых кампаниях с высоким потенциалом
        young_reliable = [c for c in high_reliability if c['campaign_age_days'] < 30]
        if young_reliable:
            message = f"Найдено {len(young_reliable)} молодых кампаний (< 30 дней) с высокой надежностью"
            message += "\n\nЭто быстрые победители, которые показали хорошие результаты за короткий срок"

            alerts.append({
                "type": "young_reliable_campaigns",
                "severity": "low",
                "message": message,
                "recommended_action": "Рассмотрите приоритетное масштабирование этих перспективных кампаний",
                "campaigns_count": len(young_reliable)
            })

        return alerts
