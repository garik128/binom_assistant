"""
Модуль оптимизации бюджета (Budget Optimizer)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
import statistics
import logging

from storage.database.base import get_session
from storage.database.models import Campaign, CampaignStatsDaily
from ..base_module import BaseModule, ModuleMetadata, ModuleConfig

logger = logging.getLogger(__name__)


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


class BudgetOptimizer(BaseModule):
    """
    Модуль оптимизации бюджета (Budget Optimizer).

    Анализирует производительность кампаний и предлагает оптимальное
    перераспределение бюджетов между ними:
    - Топ кампании по ROI -> рекомендация увеличения бюджета
    - Худшие кампании -> рекомендация снижения/остановки
    - Расчет потенциального улучшения ROI портфеля
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="budget_optimizer",
            name="Оптимизация бюджета",
            category="portfolio",
            description="Предлагает оптимальное перераспределение бюджетов между кампаниями",
            detailed_description="Модуль анализирует ROI, волатильность и риски для каждой кампании, выявляет лучшие и худшие исполнители, и рекомендует перераспределение бюджета для максимизации общего ROI портфеля.",
            version="1.1.0",
            author="Binom Assistant",
            priority="high",
            tags=["budget", "roi", "optimization", "reallocation"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Некритический модуль - не запускать автоматически
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=60,
            cache_ttl_seconds=3600,
            params={
                "days": 7,
                "max_change_percent": 30,
                "min_cost": 1.0,  # минимальный расход для анализа
                "min_clicks": 50,  # минимальное количество кликов
                "severity_warning": 10,  # потенциальное улучшение для warning severity (%)
                "severity_info": 5  # потенциальное улучшение для info severity (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа кампаний",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "max_change_percent": {
                "label": "Макс. изменение бюджета (%)",
                "description": "Максимальный процент изменения бюджета в одной рекомендации",
                "type": "number",
                "min": 5,
                "max": 100,
                "default": 30
            },
            "min_cost": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход для включения кампании в анализ",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "default": 1.0
            },
            "min_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов для включения кампании",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 50
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "potential_improvement",
            "metric_label": "Потенциальное улучшение ROI",
            "metric_unit": "%",
            "description": "Пороги критичности на основе потенциального улучшения ROI портфеля",
            "thresholds": {
                "severity_warning": {
                    "label": "Порог предупреждения",
                    "description": "Потенциальное улучшение выше этого значения требует внимания",
                    "type": "number",
                    "min": 1,
                    "max": 50,
                    "step": 1,
                    "default": 10
                },
                "severity_info": {
                    "label": "Порог информации",
                    "description": "Потенциальное улучшение выше этого значения показывается как информация",
                    "type": "number",
                    "min": 1,
                    "max": 50,
                    "step": 1,
                    "default": 5
                }
            },
            "levels": [
                {"value": "warning", "label": "Требуется оптимизация", "color": "#f59e0b", "condition": "potential_improvement > warning"},
                {"value": "info", "label": "Есть потенциал", "color": "#3b82f6", "condition": "info < potential_improvement <= warning"},
                {"value": "info", "label": "Хорошо оптимизирован", "color": "#10b981", "condition": "potential_improvement <= info"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ оптимизации бюджета.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Рекомендации по оптимизации бюджета
        """
        # Получение параметров
        days = config.params.get("days", 7)
        max_change_percent = config.params.get("max_change_percent", 30)
        min_cost = config.params.get("min_cost", 1.0)
        min_clicks = config.params.get("min_clicks", 50)

        date_from = datetime.now().date() - timedelta(days=days - 1)
        date_to = datetime.now().date()

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с их статистикой
            campaigns_data = self._get_campaigns_performance(
                session, date_from, date_to
            )

            if not campaigns_data:
                return {
                    "recommendations": [],
                    "potential_roi_improvement": 0,
                    "summary": {
                        "total_campaigns": 0,
                        "top_campaigns": 0,
                        "bottom_campaigns": 0,
                        "total_current_spend": 0,
                        "estimated_new_spend": 0
                    },
                    "period": {
                        "days": days,
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat()
                    }
                }

            # Фильтруем по минимальному расходу
            filtered_campaigns = self._filter_noise(campaigns_data, min_cost, min_clicks)

            if not filtered_campaigns:
                return {
                    "recommendations": [],
                    "potential_roi_improvement": 0,
                    "summary": {
                        "total_campaigns": 0,
                        "top_campaigns": 0,
                        "bottom_campaigns": 0,
                        "total_current_spend": 0,
                        "estimated_new_spend": 0
                    },
                    "period": {
                        "days": days,
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat()
                    }
                }

            # Генерируем рекомендации
            recommendations = self._generate_recommendations(
                filtered_campaigns, max_change_percent, days
            )

            # Рассчитываем потенциальное улучшение
            potential_improvement = self._calculate_potential_improvement(
                filtered_campaigns, recommendations
            )

            # Подготавливаем summary
            total_spend = sum(c["daily_spend"] * days for c in filtered_campaigns)
            estimated_new_spend = self._calculate_estimated_spend(
                filtered_campaigns, recommendations, days
            )

            # Получаем настраиваемые пороги severity
            severity_warning_threshold = config.params.get("severity_warning", 10)
            severity_info_threshold = config.params.get("severity_info", 5)

            return {
                "recommendations": recommendations,
                "potential_roi_improvement": potential_improvement,
                "summary": {
                    "total_campaigns": len(filtered_campaigns),
                    "top_campaigns": len([r for r in recommendations if r["change_percent"] > 0]),
                    "bottom_campaigns": len([r for r in recommendations if r["change_percent"] < 0]),
                    "total_current_spend": round(total_spend, 2),
                    "estimated_new_spend": round(estimated_new_spend, 2)
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat()
                },
                "severity_warning": severity_warning_threshold,
                "severity_info": severity_info_threshold
            }

    def _get_campaigns_performance(
        self, session, date_from: any, date_to: any
    ) -> List[Dict[str, Any]]:
        """
        Получает производительность всех кампаний за период.

        Args:
            session: DB сессия
            date_from: Начало периода
            date_to: Конец периода

        Returns:
            List[Dict]: Список с метриками кампаний
        """
        campaigns = session.query(Campaign).all()
        result = []

        for campaign in campaigns:
            # Получаем дневную статистику
            daily_stats = (
                session.query(CampaignStatsDaily)
                .filter(
                    CampaignStatsDaily.campaign_id == campaign.internal_id,
                    CampaignStatsDaily.date >= date_from,
                    CampaignStatsDaily.date <= date_to
                )
                .all()
            )

            if not daily_stats:
                continue

            # Агрегируем метрики
            total_cost = sum(float(s.cost) if s.cost else 0 for s in daily_stats)
            total_revenue = sum(float(s.revenue) if s.revenue else 0 for s in daily_stats)
            total_leads = sum(float(s.leads) if s.leads else 0 for s in daily_stats)
            total_clicks = sum(float(s.clicks) if s.clicks else 0 for s in daily_stats)
            num_days = len(daily_stats)

            # Пропускаем кампании без расхода
            if total_cost == 0:
                continue

            # Рассчитываем ROI
            roi = ((total_revenue - total_cost) / total_cost) * 100 if total_cost > 0 else 0

            # Волатильность ROI
            daily_roi_values = []
            for stat in daily_stats:
                cost = float(stat.cost) if stat.cost else 0
                revenue = float(stat.revenue) if stat.revenue else 0
                if cost > 0:
                    daily_roi = ((revenue - cost) / cost) * 100
                    daily_roi_values.append(daily_roi)

            volatility = 0
            if len(daily_roi_values) > 1:
                try:
                    mean_roi = statistics.mean(daily_roi_values)
                    stdev_roi = statistics.stdev(daily_roi_values)
                    volatility = (stdev_roi / abs(mean_roi)) * 100 if abs(mean_roi) > 0 else stdev_roi
                except Exception:
                    volatility = 0

            # Средневзвешенный CPC/CPL
            avg_cpc = total_cost / total_clicks if total_clicks > 0 else 0.0
            avg_cpl = total_cost / total_leads if total_leads > 0 else 0.0

            # Средний дневной расход
            daily_spend = total_cost / num_days if num_days > 0 else 0

            result.append({
                "campaign_id": campaign.internal_id,
                "name": campaign.current_name,
                "total_cost": total_cost,
                "total_revenue": total_revenue,
                "roi": roi,
                "volatility": volatility,
                "daily_spend": daily_spend,
                "num_days": num_days,
                "total_clicks": total_clicks,
                "total_leads": total_leads,
                "avg_cpc": avg_cpc,
                "avg_cpl": avg_cpl
            })

        return result

    def _filter_noise(self, campaigns: List[Dict[str, Any]], min_cost: float = 1.0, min_clicks: int = 50) -> List[Dict[str, Any]]:
        """
        Фильтрует маленькие кампании (шум).

        Args:
            campaigns: Список кампаний
            min_cost: Минимальный расход ($)
            min_clicks: Минимальное количество кликов

        Returns:
            List[Dict]: Отфильтрованный список
        """
        return [
            c for c in campaigns
            if c["total_cost"] >= min_cost and c["total_clicks"] >= min_clicks
        ]

    def _generate_recommendations(
        self, campaigns: List[Dict[str, Any]], max_change_percent: float, days: int
    ) -> List[Dict[str, Any]]:
        """
        Генерирует рекомендации по перераспределению бюджета.

        Логика:
        1. Сортируем по ROI
        2. Топ 20% -> рекомендуем увеличить
        3. Низ 20% -> рекомендуем снизить
        4. Учитываем волатильность как риск

        Args:
            campaigns: Список кампаний с метриками
            max_change_percent: Максимальное изменение в %
            days: Количество дней в периоде

        Returns:
            List[Dict]: Список рекомендаций
        """
        if not campaigns or len(campaigns) < 2:
            return []

        # Сортируем по ROI
        sorted_campaigns = sorted(campaigns, key=lambda x: x["roi"], reverse=True)

        # Определяем границы топ и bottom групп
        num_top = max(1, len(sorted_campaigns) // 5)
        num_bottom = max(1, len(sorted_campaigns) // 5)

        top_campaigns = sorted_campaigns[:num_top]
        bottom_campaigns = sorted_campaigns[-num_bottom:]

        recommendations = []

        # Рекомендации для топ кампаний
        for campaign in top_campaigns:
            # ИСПРАВЛЕНО: Более эффективная логика штрафа за волатильность
            # Высокая волатильность должна значительно снижать рекомендуемое увеличение
            roi_score = min(campaign["roi"] / 100, 1.0)  # Нормализуем ROI

            # Волатильность > 100% получает максимальный штраф
            # Штраф масштабируется нелинейно для более сильного эффекта
            volatility = campaign["volatility"]
            if volatility > 150:
                # Критическая волатильность - минимальное увеличение
                volatility_factor = 0.1
            elif volatility > 100:
                # Очень высокая волатильность - сильный штраф
                volatility_factor = 0.3
            elif volatility > 50:
                # Высокая волатильность - средний штраф
                volatility_factor = 0.6
            else:
                # Низкая волатильность - минимальный штраф
                volatility_factor = 1.0

            change_percent = roi_score * max_change_percent * volatility_factor

            change_percent = min(change_percent, max_change_percent)
            change_percent = max(change_percent, 5)  # Минимум 5%

            new_daily_spend = campaign["daily_spend"] * (1 + change_percent / 100)

            recommendations.append({
                "campaign_id": campaign["campaign_id"],
                "name": campaign["name"],
                "current_daily_spend": round(campaign["daily_spend"], 2),
                "recommended_daily_spend": round(new_daily_spend, 2),
                "change_percent": round(change_percent, 1),
                "reason": self._get_reason_for_increase(campaign),
                "current_roi": round(campaign["roi"], 1),
                "current_volatility": round(campaign["volatility"], 1)
            })

        # Рекомендации для bottom кампаний
        for campaign in bottom_campaigns:
            if campaign in top_campaigns:  # Не добавляем дважды
                continue

            roi_score = max(campaign["roi"], -100) / 100
            volatility_risk = campaign["volatility"] / 100

            change_percent = roi_score * max_change_percent + volatility_risk * 5
            change_percent = max(change_percent, -max_change_percent)
            change_percent = min(change_percent, -5)  # Минимум -5%

            new_daily_spend = campaign["daily_spend"] * (1 + change_percent / 100)

            recommendations.append({
                "campaign_id": campaign["campaign_id"],
                "name": campaign["name"],
                "current_daily_spend": round(campaign["daily_spend"], 2),
                "recommended_daily_spend": round(new_daily_spend, 2),
                "change_percent": round(change_percent, 1),
                "reason": self._get_reason_for_decrease(campaign),
                "current_roi": round(campaign["roi"], 1),
                "current_volatility": round(campaign["volatility"], 1)
            })

        # Сортируем по величине изменения (убывание)
        recommendations.sort(key=lambda x: abs(x["change_percent"]), reverse=True)

        return recommendations

    def _get_reason_for_increase(self, campaign: Dict[str, Any]) -> str:
        """Возвращает причину для увеличения бюджета"""
        roi = campaign["roi"]
        volatility = campaign["volatility"]

        if roi > 50 and volatility < 30:
            return "Высокий ROI, низкая волатильность"
        elif roi > 50:
            return "Высокий ROI, но повышенные риски"
        elif roi > 0 and volatility < 20:
            return "Стабильная прибыльная кампания"
        else:
            return "Хорошая производительность"

    def _get_reason_for_decrease(self, campaign: Dict[str, Any]) -> str:
        """Возвращает причину для снижения бюджета"""
        roi = campaign["roi"]
        volatility = campaign["volatility"]

        if roi < -50:
            return "Критический убыток"
        elif roi < -20:
            return "Значительный убыток"
        elif roi < 0:
            return "Убыточная кампания"
        elif volatility > 100:
            return "Высокие риски, неустойчивая производительность"
        else:
            return "Низкая производительность"

    def _calculate_potential_improvement(
        self, campaigns: List[Dict[str, Any]], recommendations: List[Dict[str, Any]]
    ) -> float:
        """
        Рассчитывает потенциальное улучшение ROI портфеля.

        Args:
            campaigns: Список кампаний
            recommendations: Список рекомендаций

        Returns:
            float: Потенциальное улучшение в %
        """
        if not campaigns or not recommendations:
            return 0

        # Текущий средневзвешенный ROI
        total_cost = sum(c["total_cost"] for c in campaigns)
        if total_cost == 0:
            return 0

        current_weighted_roi = sum(
            c["roi"] * c["total_cost"] for c in campaigns
        ) / total_cost

        # ИСПРАВЛЕНО: Используем правильный расчет взвешенного ROI
        # ROI кампании остается неизменным, меняется только ее вес в портфеле

        # Создаем словарь рекомендаций для быстрого доступа
        rec_dict = {r["campaign_id"]: r for r in recommendations}

        # Для каждой кампании рассчитываем новую стоимость
        new_campaigns_cost = {}
        for campaign in campaigns:
            if campaign["campaign_id"] in rec_dict:
                rec = rec_dict[campaign["campaign_id"]]
                # Новая стоимость = текущая стоимость * коэффициент изменения
                change_factor = 1 + rec["change_percent"] / 100
                new_cost = campaign["total_cost"] * change_factor
                new_campaigns_cost[campaign["campaign_id"]] = new_cost
            else:
                new_campaigns_cost[campaign["campaign_id"]] = campaign["total_cost"]

        # Рассчитываем новый взвешенный ROI правильно
        # Новый взвешенный ROI = сумма(ROI_i * новая_стоимость_i) / сумма(новая_стоимость_i)
        new_total_cost = sum(new_campaigns_cost.values())
        if new_total_cost > 0:
            new_weighted_roi = sum(
                c["roi"] * new_campaigns_cost[c["campaign_id"]]
                for c in campaigns
            ) / new_total_cost
        else:
            new_weighted_roi = current_weighted_roi

        # Рассчитываем улучшение
        if abs(current_weighted_roi) > 0:
            improvement = ((new_weighted_roi - current_weighted_roi) / abs(current_weighted_roi)) * 100
        else:
            improvement = new_weighted_roi * 100 if new_weighted_roi != 0 else 0

        return max(improvement, 0)  # Не показываем отрицательные значения

    def _calculate_estimated_spend(
        self, campaigns: List[Dict[str, Any]], recommendations: List[Dict[str, Any]], days: int
    ) -> float:
        """
        Рассчитывает предполагаемый новый расход.

        Args:
            campaigns: Список кампаний
            recommendations: Список рекомендаций
            days: Количество дней в периоде

        Returns:
            float: Предполагаемый новый расход
        """
        rec_dict = {r["campaign_id"]: r for r in recommendations}

        total_new_spend = 0
        for campaign in campaigns:
            if campaign["campaign_id"] in rec_dict:
                rec = rec_dict[campaign["campaign_id"]]
                total_new_spend += rec["recommended_daily_spend"] * days
            else:
                total_new_spend += campaign["daily_spend"] * days

        return total_new_spend

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация текстовых рекомендаций.
        """
        recommendations_list = raw_data.get("recommendations", [])
        potential_improvement = raw_data.get("potential_roi_improvement", 0)
        summary = raw_data.get("summary", {})

        tips = []

        if potential_improvement > 0:
            tips.append(
                f"Следуя этим рекомендациям, вы можете улучшить ROI портфеля на {potential_improvement:.1f}%"
            )

        if summary.get("top_campaigns", 0) > 0:
            tips.append(
                f"Рассмотрите увеличение бюджета для {summary['top_campaigns']} топ-исполнителей"
            )

        if summary.get("bottom_campaigns", 0) > 0:
            tips.append(
                f"Сосредоточьтесь на оптимизации или остановке {summary['bottom_campaigns']} низкопроизводительных кампаний"
            )

        spend_diff = summary.get("estimated_new_spend", 0) - summary.get("total_current_spend", 0)
        if abs(spend_diff) > 0.01:
            if spend_diff > 0:
                tips.append(
                    f"Общий бюджет может увеличиться на ${spend_diff:.2f} для достижения оптимального распределения"
                )
            else:
                tips.append(
                    f"Общий бюджет может быть снижен на ${abs(spend_diff):.2f} без потери ROI"
                )

        return tips

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        recommendations = raw_data.get("recommendations", [])
        potential_improvement = raw_data.get("potential_roi_improvement", 0)

        charts = []

        if recommendations:
            # Диаграмма сравнения текущего и рекомендуемого бюджета
            charts.append({
                "id": "budget_optimizer_comparison",
                "type": "bar",
                "data": {
                    "labels": [r["name"][:30] for r in recommendations[:10]],
                    "datasets": [
                        {
                            "label": "Текущий дневной бюджет",
                            "data": [r["current_daily_spend"] for r in recommendations[:10]],
                            "backgroundColor": "rgba(100, 150, 200, 0.7)"
                        },
                        {
                            "label": "Рекомендуемый бюджет",
                            "data": [r["recommended_daily_spend"] for r in recommendations[:10]],
                            "backgroundColor": "rgba(40, 167, 69, 0.7)"
                        }
                    ]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Сравнение бюджетов (топ 10)"
                        },
                        "legend": {
                            "position": "bottom"
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "ticks": {
                                "callback": "function(value) { return '$' + value.toFixed(2); }"
                            }
                        }
                    }
                }
            })

            # Диаграмма изменения бюджета (%)
            top_recommendations = sorted(
                recommendations, key=lambda x: abs(x["change_percent"]), reverse=True
            )[:8]

            charts.append({
                "id": "budget_optimizer_changes",
                "type": "bar",
                "data": {
                    "labels": [r["name"][:30] for r in top_recommendations],
                    "datasets": [{
                        "label": "Изменение бюджета (%)",
                        "data": [r["change_percent"] for r in top_recommendations],
                        "backgroundColor": [
                            "rgba(40, 167, 69, 0.7)" if r["change_percent"] > 0 else "rgba(220, 53, 69, 0.7)"
                            for r in top_recommendations
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Рекомендуемые изменения бюджета"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "ticks": {
                                "callback": "function(value) { return value + '%'; }"
                            }
                        }
                    }
                }
            })

        # Информационная диаграмма
        charts.append({
            "id": "budget_optimizer_improvement",
            "type": "doughnut",
            "data": {
                "labels": ["Потенциал улучшения", "Текущее состояние"],
                "datasets": [{
                    "data": [potential_improvement, 100 - potential_improvement],
                    "backgroundColor": ["rgba(40, 167, 69, 0.8)", "rgba(200, 200, 200, 0.3)"]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Потенциальное улучшение ROI: {potential_improvement:.1f}%"
                    },
                    "legend": {
                        "position": "bottom"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { return context.label + ': ' + context.parsed + '%'; }"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для оптимизации бюджета.
        """
        recommendations = raw_data.get("recommendations", [])
        potential_improvement = raw_data.get("potential_roi_improvement", 0)
        summary = raw_data.get("summary", {})

        # Получаем настраиваемые пороги severity
        severity_warning_threshold = raw_data.get("severity_warning", 10)
        severity_info_threshold = raw_data.get("severity_info", 5)

        alerts = []

        if not recommendations:
            return alerts

        # Основной алерт с настраиваемыми порогами
        if potential_improvement > severity_warning_threshold:
            severity = "warning"
            title = "Значительный потенциал для оптимизации"
        elif potential_improvement > severity_info_threshold:
            severity = "info"
            title = "Есть возможность улучшить ROI"
        else:
            severity = "info"
            title = "Портфель относительно хорошо оптимизирован"

        message = f"Анализ показывает потенциальное улучшение ROI на {potential_improvement:.1f}%\n\n"
        message += f"Рекомендуется:\n"
        message += f"• Увеличить бюджет {summary.get('top_campaigns', 0)} топ-кампаний\n"
        message += f"• Сократить бюджет {summary.get('bottom_campaigns', 0)} низкопроизводительных кампаний\n"

        if summary.get("top_campaigns", 0) > 0:
            message += f"\nТоп-кампании для увеличения бюджета:\n"
            for rec in [r for r in recommendations if r["change_percent"] > 0][:3]:
                message += f"• {rec['name']}: +{rec['change_percent']:.0f}% ({rec['reason']})\n"

        if summary.get("bottom_campaigns", 0) > 0:
            message += f"\nКампании для снижения бюджета:\n"
            for rec in [r for r in recommendations if r["change_percent"] < 0][:3]:
                message += f"• {rec['name']}: {rec['change_percent']:.0f}% ({rec['reason']})\n"

        alerts.append({
            "type": "budget_optimization",
            "severity": severity,
            "title": title,
            "message": message,
            "potential_improvement": round(potential_improvement, 1),
            "total_campaigns": summary.get("total_campaigns", 0),
            "top_campaigns_count": summary.get("top_campaigns", 0),
            "bottom_campaigns_count": summary.get("bottom_campaigns", 0)
        })

        return alerts
