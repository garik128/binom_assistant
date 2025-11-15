"""
Модуль оценки консистентности прибыли
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


class ConsistencyScorer(BaseModule):
    """
    Оценка стабильности прибыли во времени.

    Анализирует консистентность прибыли используя различные статистические метрики.
    Выявляет надежные кампании для масштабирования.

    Логика оценки консистентности:
    - Процент прибыльных дней из последних N дней
    - Максимальная просадка (drawdown)
    - Соотношение прибыльных/убыточных дней
    - Индекс стабильности от 0 до 100
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="consistency_scorer",
            name="Стабильность",
            category="stability",
            description="Оценка стабильности прибыли во времени",
            detailed_description=(
                "Модуль анализирует консистентность прибыли используя различные статистические метрики. "
                "Помогает выявить надежные кампании для масштабирования на основе процента прибыльных дней, "
                "максимальной просадки и соотношения прибыльных/убыточных дней."
            ),
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["consistency", "stability", "profitability", "reliability"]
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
                "profitability_threshold": 70,  # Порог для высокой консистентности (% прибыльных дней)
                "severity_high": 70,  # Порог высокой консистентности (индекс >= 70)
                "severity_medium": 40,  # Порог средней консистентности (индекс >= 40)
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
                "description": "Количество дней для расчета консистентности (включая сегодня)",
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
            },
            "profitability_threshold": {
                "label": "Порог высокой консистентности (%)",
                "description": "Минимальный процент прибыльных дней для высокой консистентности",
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
            "metric": "consistency_score",
            "metric_label": "Индекс консистентности",
            "metric_unit": "",
            "description": "Пороги критичности на основе индекса консистентности (0-100). Высокий индекс = хорошо",
            "inverted": False,
            "thresholds": {
                "severity_high": {
                    "label": "Порог высокой консистентности",
                    "description": "Индекс выше этого значения считается высоким (хорошо)",
                    "type": "number",
                    "min": 50,
                    "max": 100,
                    "step": 5,
                    "default": 70
                },
                "severity_medium": {
                    "label": "Порог средней консистентности",
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
        Анализ консистентности прибыли через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о консистентности кампаний
        """
        # Получение параметров
        days = config.params.get("days", 14)
        min_spend = config.params.get("min_spend", 1)
        min_days_with_data = config.params.get("min_days_with_data", 7)
        profitability_threshold = config.params.get("profitability_threshold", 70)

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
                CampaignStatsDaily.revenue
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
                profit = revenue - cost

                campaigns_data[campaign_id].append({
                    'date': row.date,
                    'cost': cost,
                    'revenue': revenue,
                    'profit': profit,
                    'is_profitable': profit > 0
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

            # Анализируем консистентность для каждой кампании
            high_consistency = []
            medium_consistency = []
            low_consistency = []

            for campaign_id, daily_data in campaigns_data.items():
                # Пропускаем если недостаточно данных
                if len(daily_data) < min_days_with_data:
                    continue

                # Количество прибыльных и убыточных дней
                profitable_days = sum(1 for d in daily_data if d['is_profitable'])
                unprofitable_days = len(daily_data) - profitable_days

                # Процент прибыльных дней
                profitable_days_pct = round((profitable_days / len(daily_data) * 100), 2)

                # Соотношение прибыльных к убыточным
                if unprofitable_days > 0:
                    profit_loss_ratio = round(profitable_days / unprofitable_days, 2)
                else:
                    profit_loss_ratio = round(float(profitable_days), 2)

                # Расчет максимальной просадки (drawdown)
                cumulative_profit = 0
                peak_profit = 0
                max_drawdown = 0
                max_drawdown_pct = 0

                for d in daily_data:
                    cumulative_profit += d['profit']

                    if cumulative_profit > peak_profit:
                        peak_profit = cumulative_profit

                    drawdown = peak_profit - cumulative_profit
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown

                # Процент максимальной просадки (от пикового значения)
                if peak_profit > 0:
                    max_drawdown_pct = round((max_drawdown / peak_profit * 100), 2)
                else:
                    max_drawdown_pct = 0

                # Агрегированные показатели за весь период
                total_cost = sum(d['cost'] for d in daily_data)
                total_revenue = sum(d['revenue'] for d in daily_data)
                total_profit = total_revenue - total_cost
                avg_roi = round(((total_revenue - total_cost) / total_cost * 100), 2) if total_cost > 0 else 0

                # Индекс консистентности (0-100)
                # 50% - процент прибыльных дней (чем больше, тем лучше)
                # 30% - соотношение прибыль/убыток (макс 10:1 = 100%)
                # 20% - инверсия просадки (чем меньше просадка, тем лучше)

                score_profitable_days = profitable_days_pct * 0.5  # 0-50 баллов
                score_ratio = min(profit_loss_ratio / 10 * 30, 30)  # 0-30 баллов (макс при 10:1)
                score_drawdown = max(0, (100 - max_drawdown_pct)) * 0.2  # 0-20 баллов

                consistency_score = round(score_profitable_days + score_ratio + score_drawdown, 2)

                # Классификация консистентности на основе настраиваемых порогов
                # Высокая: индекс >= severity_high
                # Средняя: индекс >= severity_medium (но < severity_high)
                # Низкая: индекс < severity_medium
                if consistency_score >= severity_high_threshold:
                    consistency_class = "high"
                    severity = "low"  # Хорошая новость
                elif consistency_score >= severity_medium_threshold:
                    consistency_class = "medium"
                    severity = "medium"
                else:
                    consistency_class = "low"
                    severity = "high"

                # Формируем данные
                full_campaign_info = campaigns_info.get(campaign_id, {
                    'binom_id': None,
                    'name': f"Campaign {campaign_id}",
                    'group': "Без группы",
                    'is_cpl_mode': False
                })

                campaign_consistency = {
                    "campaign_id": campaign_id,
                    "binom_id": full_campaign_info['binom_id'],
                    "name": full_campaign_info['name'],
                    "group": full_campaign_info['group'],

                    # Агрегированные метрики
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2),
                    "total_profit": round(total_profit, 2),
                    "avg_roi": avg_roi,

                    # Метрики консистентности
                    "consistency_score": consistency_score,
                    "consistency_class": consistency_class,
                    "profitable_days": profitable_days,
                    "unprofitable_days": unprofitable_days,
                    "profitable_days_pct": profitable_days_pct,
                    "profit_loss_ratio": profit_loss_ratio,
                    "max_drawdown": round(max_drawdown, 2),
                    "max_drawdown_pct": max_drawdown_pct,

                    # Дополнительные данные
                    "days_with_data": len(daily_data),
                    "severity": severity,
                    "is_cpl_mode": full_campaign_info.get('is_cpl_mode', False)
                }

                # Распределяем по категориям
                if consistency_class == "high":
                    high_consistency.append(campaign_consistency)
                elif consistency_class == "medium":
                    medium_consistency.append(campaign_consistency)
                else:
                    low_consistency.append(campaign_consistency)

            # Сортировка (по убыванию индекса консистентности)
            high_consistency.sort(key=lambda x: x['consistency_score'], reverse=True)
            medium_consistency.sort(key=lambda x: x['consistency_score'], reverse=True)
            low_consistency.sort(key=lambda x: x['consistency_score'])

            # Объединяем для общей таблицы (сначала наиболее консистентные)
            all_campaigns = high_consistency + medium_consistency + low_consistency

            return {
                "campaigns": all_campaigns,
                "high_consistency": high_consistency,
                "medium_consistency": medium_consistency,
                "low_consistency": low_consistency,
                "summary": {
                    "total_analyzed": len(all_campaigns),
                    "total_high": len(high_consistency),
                    "total_medium": len(medium_consistency),
                    "total_low": len(low_consistency),
                    "avg_consistency_score": round(
                        sum(c['consistency_score'] for c in all_campaigns) / len(all_campaigns), 2
                    ) if all_campaigns else 0,
                    "best_consistency_score": round(high_consistency[0]['consistency_score'], 2) if high_consistency else 0,
                    "worst_consistency_score": round(low_consistency[-1]['consistency_score'], 2) if low_consistency else 0,
                    "avg_profitable_days_pct": round(
                        sum(c['profitable_days_pct'] for c in all_campaigns) / len(all_campaigns), 2
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
                    "profitability_threshold": profitability_threshold,
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
        high_consistency = raw_data["high_consistency"][:10]
        low_consistency = raw_data["low_consistency"][:10]

        charts = []

        # График: Высокая консистентность (топ-10)
        if high_consistency:
            charts.append({
                "id": "high_consistency_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in high_consistency],
                    "datasets": [{
                        "label": "Индекс консистентности",
                        "data": [c["consistency_score"] for c in high_consistency],
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
                            "text": "Топ-10 наиболее консистентных кампаний"
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

        # График: Низкая консистентность (худшие 10)
        if low_consistency:
            charts.append({
                "id": "low_consistency_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in low_consistency],
                    "datasets": [{
                        "label": "Индекс консистентности",
                        "data": [c["consistency_score"] for c in low_consistency],
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
                            "text": "Топ-10 наименее консистентных кампаний"
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

        # Doughnut: Распределение по уровням консистентности
        summary = raw_data["summary"]
        if summary["total_analyzed"] > 0:
            charts.append({
                "id": "consistency_distribution",
                "type": "doughnut",
                "data": {
                    "labels": [
                        f"Высокая (≥{raw_data['thresholds']['profitability_threshold']})",
                        f"Средняя (40-{raw_data['thresholds']['profitability_threshold']})",
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
                            "text": "Распределение по уровням консистентности"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кампаний с низкой консистентностью.
        """
        alerts = []
        summary = raw_data["summary"]
        high_consistency = raw_data["high_consistency"]
        low_consistency = raw_data["low_consistency"]

        # Алерт о кампаниях с высокой консистентностью (возможности для масштабирования)
        if high_consistency:
            top_3 = high_consistency[:3]
            message = f"Найдено {len(high_consistency)} стабильных кампаний для масштабирования"
            message += "\n\nТоп-3 наиболее консистентных:"
            for i, camp in enumerate(top_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['consistency_score']:.1f}, прибыльных дней {camp['profitable_days_pct']:.1f}%"

            alerts.append({
                "type": "high_consistency_opportunities",
                "severity": "low",
                "message": message,
                "recommended_action": "Эти кампании показывают стабильную прибыль и подходят для увеличения бюджета",
                "campaigns_count": len(high_consistency)
            })

        # Алерт о кампаниях с низкой консистентностью
        if low_consistency:
            worst_3 = low_consistency[:3]
            message = f"ВНИМАНИЕ: {len(low_consistency)} кампаний с низкой консистентностью прибыли"
            message += "\n\nТоп-3 наименее стабильных:"
            for i, camp in enumerate(worst_3, 1):
                message += f"\n{i}. {camp['name']}: индекс {camp['consistency_score']:.1f}, прибыльных дней {camp['profitable_days_pct']:.1f}%"

            alerts.append({
                "type": "low_consistency_warning",
                "severity": "high",
                "message": message,
                "recommended_action": "Рассмотрите снижение бюджета или остановку нестабильных кампаний",
                "campaigns_count": len(low_consistency)
            })

        # Алерт о высокой доле нестабильных кампаний в портфеле
        if summary["total_analyzed"] > 0:
            low_consistency_pct = (summary["total_low"] / summary["total_analyzed"]) * 100
            if low_consistency_pct > 40:
                message = f"Высокая доля нестабильных кампаний в портфеле: {low_consistency_pct:.1f}%"
                message += f"\n\nНестабильных: {summary['total_low']}"
                message += f"\nСредней стабильности: {summary['total_medium']}"
                message += f"\nСтабильных: {summary['total_high']}"

                alerts.append({
                    "type": "portfolio_instability",
                    "severity": "medium",
                    "message": message,
                    "recommended_action": "Перераспределите бюджет в пользу более консистентных кампаний для снижения рисков",
                    "campaigns_count": summary["total_low"]
                })

        return alerts
