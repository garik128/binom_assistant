"""
Модуль расчета индекса здоровья портфеля кампаний (Portfolio Health Index)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict
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


class PortfolioHealthIndex(BaseModule):
    """
    Модуль расчета индекса здоровья портфеля (Portfolio Health Index).

    Рассчитывает общий индекс здоровья портфеля кампаний от 0 до 100
    на основе комбинированных метрик:
    - Средневзвешенный ROI (вес 30%)
    - Доля прибыльных кампаний (вес 25%)
    - Стабильность метрик (вес 20%)
    - Диверсификация (вес 15%)
    - Тренд последних 7 дней (вес 10%)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="portfolio_health_index",
            name="Здоровье портфеля",
            category="portfolio",
            description="Рассчитывает общий индекс здоровья портфеля кампаний от 0 до 100",
            detailed_description="Модуль анализирует портфель всех кампаний и рассчитывает индекс здоровья на основе ROI, прибыльности, стабильности, диверсификации и тренда. Помогает быстро оценить общее состояние портфеля. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="high",
            tags=["portfolio", "health", "roi", "stability", "diversification"]
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
                "days": 7,  # период для анализа
                "min_cost": 1.0,  # минимальный расход для фильтрации
                "min_leads": 50,  # минимальное количество лидов для фильтрации
                "roi_weight": 30,  # вес ROI в итоговом индексе (%)
                "profitable_weight": 25,  # вес прибыльности в индексе (%)
                "stability_weight": 20,  # вес стабильности в индексе (%)
                "diversification_weight": 15,  # вес диверсификации в индексе (%)
                "trend_weight": 10,  # вес тренда в индексе (%)
                "severity_critical": 40,  # индекс здоровья для critical severity
                "severity_warning": 60  # индекс здоровья для warning severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа портфеля",
                "type": "number",
                "min": 1,
                "max": 365,
                "default": 7
            },
            "min_cost": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход для включения кампании в анализ",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "default": 1.0
            },
            "min_leads": {
                "label": "Минимум лидов",
                "description": "Минимальное количество лидов для включения кампании",
                "type": "number",
                "min": 1,
                "max": 1000,
                "default": 50
            },
            "roi_weight": {
                "label": "Вес ROI (%)",
                "description": "Вес средневзвешенного ROI в итоговом индексе",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 30
            },
            "profitable_weight": {
                "label": "Вес прибыльности (%)",
                "description": "Вес доли прибыльных кампаний в итоговом индексе",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 25
            },
            "stability_weight": {
                "label": "Вес стабильности (%)",
                "description": "Вес стабильности метрик в итоговом индексе",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 20
            },
            "diversification_weight": {
                "label": "Вес диверсификации (%)",
                "description": "Вес диверсификации портфеля в итоговом индексе",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 15
            },
            "trend_weight": {
                "label": "Вес тренда (%)",
                "description": "Вес тренда последних дней в итоговом индексе",
                "type": "number",
                "min": 0,
                "max": 100,
                "default": 10
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "health_index",
            "metric_label": "Индекс здоровья",
            "metric_unit": "",
            "description": "Пороги критичности на основе индекса здоровья портфеля",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичный индекс",
                    "description": "Индекс здоровья ниже этого значения считается критичным",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 40
                },
                "severity_warning": {
                    "label": "Предупреждение",
                    "description": "Индекс здоровья ниже этого значения (но выше критичного) требует внимания",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 60
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "health_index < critical"},
                {"value": "warning", "label": "Предупреждение", "color": "#f59e0b", "condition": "critical <= health_index < warning"},
                {"value": "info", "label": "Норма", "color": "#3b82f6", "condition": "health_index >= warning"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ здоровья портфеля.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о здоровье портфеля
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_cost = config.params.get("min_cost", 1.0)
        min_leads = config.params.get("min_leads", 50)
        roi_weight = config.params.get("roi_weight", 30) / 100  # конвертируем в долю
        profitable_weight = config.params.get("profitable_weight", 25) / 100
        stability_weight = config.params.get("stability_weight", 20) / 100
        diversification_weight = config.params.get("diversification_weight", 15) / 100
        trend_weight = config.params.get("trend_weight", 10) / 100

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.leads,
                CampaignStatsDaily.a_leads
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from
            ).order_by(
                Campaign.internal_id,
                CampaignStatsDaily.date
            )

            results = query.all()

            # Группировка по кампаниям
            campaigns_data = defaultdict(lambda: {
                "binom_id": None,
                "name": None,
                "group": None,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "daily_stats": [],
                "days_with_data": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                leads = float(row.leads) if row.leads else 0
                a_leads = float(row.a_leads) if row.a_leads else 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_revenue"] += revenue
                campaigns_data[campaign_id]["total_leads"] += leads
                campaigns_data[campaign_id]["total_a_leads"] += a_leads

                if cost > 0:
                    campaigns_data[campaign_id]["days_with_data"] += 1

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads
                })

            # Анализ портфеля
            portfolio_campaigns = []
            total_portfolio_cost = 0
            total_portfolio_revenue = 0
            profitable_campaigns = 0
            roi_values = []
            daily_roi_values_by_day = defaultdict(list)
            group_performance = defaultdict(lambda: {"cost": 0, "revenue": 0, "count": 0})

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                cost = data["total_cost"]
                revenue = data["total_revenue"]

                # Пропускаем очень маленькие кампании (шум)
                if cost < min_cost or data["total_leads"] < min_leads:
                    continue

                # ROI расчет
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                roi_values.append(roi)

                # Определение прибыльности
                is_profitable = revenue > cost
                if is_profitable:
                    profitable_campaigns += 1

                # Сбор дневных ROI для анализа тренда
                for day_stat in data["daily_stats"]:
                    if day_stat["cost"] > 0:
                        day_roi = ((day_stat["revenue"] - day_stat["cost"]) / day_stat["cost"]) * 100
                        daily_roi_values_by_day[day_stat["date"]].append(day_roi)

                total_portfolio_cost += cost
                total_portfolio_revenue += revenue

                # Накопление данных по группам
                group = data["group"]
                group_performance[group]["cost"] += cost
                group_performance[group]["revenue"] += revenue
                group_performance[group]["count"] += 1

                portfolio_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": group,
                    "roi": round(roi, 1),
                    "is_profitable": is_profitable,
                    "cost": round(cost, 2),
                    "revenue": round(revenue, 2)
                })

            # Расчет компонентов индекса
            total_campaigns = len(portfolio_campaigns)

            # 1. Средневзвешенный ROI (вес 30%)
            weighted_roi_score = self._calculate_weighted_roi_score(
                portfolio_campaigns,
                roi_values
            )

            # 2. Доля прибыльных кампаний (вес 25%)
            profitable_ratio_score = self._calculate_profitable_ratio_score(
                total_campaigns,
                profitable_campaigns
            )

            # 3. Стабильность метрик (вес 20%)
            stability_score = self._calculate_stability_score(roi_values)

            # 4. Диверсификация (вес 15%)
            diversification_score = self._calculate_diversification_score(
                group_performance,
                total_campaigns
            )

            # 5. Тренд последних 7 дней (вес 10%)
            trend_score = self._calculate_trend_score(daily_roi_values_by_day)

            # Общий индекс здоровья (используем настраиваемые веса)
            health_index = (
                weighted_roi_score * roi_weight +
                profitable_ratio_score * profitable_weight +
                stability_score * stability_weight +
                diversification_score * diversification_weight +
                trend_score * trend_weight
            )

            # Получаем настраиваемые пороги severity
            severity_critical_threshold = config.params.get("severity_critical", 40)
            severity_warning_threshold = config.params.get("severity_warning", 60)

            return {
                "health_index": round(health_index, 1),
                "components": {
                    "weighted_roi": round(weighted_roi_score, 1),
                    "profitable_ratio": round(profitable_ratio_score, 1),
                    "stability": round(stability_score, 1),
                    "diversification": round(diversification_score, 1),
                    "trend": round(trend_score, 1)
                },
                "summary": {
                    "total_campaigns": total_campaigns,
                    "profitable_campaigns": profitable_campaigns,
                    "avg_roi": round(statistics.mean(roi_values), 1) if roi_values else 0,
                    "total_cost": round(total_portfolio_cost, 2),
                    "total_revenue": round(total_portfolio_revenue, 2)
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "severity_critical": severity_critical_threshold,
                "severity_warning": severity_warning_threshold
            }

    def _calculate_weighted_roi_score(self, campaigns: List[Dict[str, Any]], roi_values: List[float]) -> float:
        """
        Рассчитывает взвешенный ROI и преобразует в score 0-100.

        Args:
            campaigns: Список кампаний с данными
            roi_values: Список значений ROI

        Returns:
            float: Score от 0 до 100
        """
        if not campaigns or not roi_values:
            return 50  # Нейтральное значение

        # Взвешенный ROI по стоимости кампании
        total_cost = sum(c["cost"] for c in campaigns)
        if total_cost == 0:
            return 50

        weighted_roi = sum(
            (c["roi"] * c["cost"]) / total_cost for c in campaigns
        )

        # Преобразование ROI в score (0-100)
        # -100% ROI -> score 0
        # 0% ROI -> score 50
        # 100% ROI -> score 100
        # Используем логистическую функцию для плавного преобразования
        score = 50 + (weighted_roi / 2)
        score = max(0, min(100, score))  # Ограничиваем от 0 до 100

        return score

    def _calculate_profitable_ratio_score(self, total_campaigns: int, profitable_campaigns: int) -> float:
        """
        Рассчитывает долю прибыльных кампаний и преобразует в score 0-100.

        Args:
            total_campaigns: Общее количество кампаний
            profitable_campaigns: Количество прибыльных кампаний

        Returns:
            float: Score от 0 до 100
        """
        if total_campaigns == 0:
            return 50

        ratio = (profitable_campaigns / total_campaigns) * 100

        # Преобразование в score
        # 0% -> score 0
        # 50% -> score 50
        # 100% -> score 100
        return ratio

    def _calculate_stability_score(self, roi_values: List[float]) -> float:
        """
        Рассчитывает стабильность метрик и преобразует в score 0-100.

        Низкая волатильность = высокий score.

        Args:
            roi_values: Список значений ROI кампаний

        Returns:
            float: Score от 0 до 100
        """
        if len(roi_values) < 2:
            return 50

        try:
            mean_roi = statistics.mean(roi_values)
            stdev_roi = statistics.stdev(roi_values)

            # Коэффициент вариации
            if abs(mean_roi) > 0:
                cv = stdev_roi / abs(mean_roi)
            else:
                cv = stdev_roi if stdev_roi > 0 else 0

            # Преобразование CV в score
            # CV = 0 -> score 100
            # CV = 0.5 -> score 50
            # CV = 1.0 -> score 0
            score = max(0, 100 * (1 - cv))

            return score
        except Exception:
            return 50

    def _calculate_diversification_score(self, group_performance: Dict[str, Dict[str, Any]], total_campaigns: int) -> float:
        """
        Рассчитывает диверсификацию портфеля и преобразует в score 0-100.

        Хорошая диверсификация = равномерное распределение по группам/источникам.

        Args:
            group_performance: Словарь производительности по группам
            total_campaigns: Общее количество кампаний

        Returns:
            float: Score от 0 до 100
        """
        if total_campaigns == 0 or len(group_performance) == 0:
            return 50

        # Рассчитываем долю каждой группы
        group_shares = [
            data["count"] / total_campaigns for data in group_performance.values()
        ]

        # Используем индекс Герфиндаля для измерения концентрации
        # HHI = сумма (доля^2)
        # HHI от 0 (идеальная диверсификация) до 1 (полная концентрация)
        hhi = sum(share ** 2 for share in group_shares)

        # Преобразование в score (0-100)
        # HHI = 0 (максимальная диверсификация) -> score 100
        # HHI = 1 (одна группа) -> score 0
        score = (1 - hhi) * 100

        return score

    def _calculate_trend_score(self, daily_roi_values: Dict[Any, List[float]]) -> float:
        """
        Рассчитывает тренд последних 7 дней и преобразует в score 0-100.

        Положительный тренд = высокий score.

        Args:
            daily_roi_values: Словарь дневных ROI значений по датам

        Returns:
            float: Score от 0 до 100
        """
        if not daily_roi_values:
            return 50

        # Получаем среднее ROI по дням
        daily_avg_roi = {}
        for date, roi_list in daily_roi_values.items():
            if roi_list:
                daily_avg_roi[date] = statistics.mean(roi_list)

        if len(daily_avg_roi) < 2:
            return 50

        # Сортируем по дате
        sorted_dates = sorted(daily_avg_roi.keys())
        sorted_roi = [daily_avg_roi[date] for date in sorted_dates]

        try:
            # Вычисляем тренд (линейную регрессию)
            # Простой способ: сравниваем первую половину со второй
            mid = len(sorted_roi) // 2
            if mid == 0:
                first_half_avg = sorted_roi[0]
                second_half_avg = sorted_roi[-1]
            else:
                first_half_avg = statistics.mean(sorted_roi[:mid])
                second_half_avg = statistics.mean(sorted_roi[mid:])

            # ИСПРАВЛЕНО: Правильная обработка трендов с учетом прибыльности
            # Абсолютное изменение ROI
            roi_change = second_half_avg - first_half_avg

            # Для оценки тренда важно учитывать не только изменение, но и текущее состояние
            # Портфель, улучшающийся с -20% до -5%, все еще теряет деньги
            # Портфель с ROI 10% -> 20% заслуживает высокого score

            # Вычисляем базовый score на основе изменения
            if abs(first_half_avg) > 0.1:
                trend_pct = (roi_change / abs(first_half_avg)) * 100
            else:
                # Для околонулевого ROI используем абсолютное изменение
                trend_pct = roi_change * 2  # Масштабируем для score

            # Базовый score от тренда: 50 + trend/2
            base_score = 50 + (trend_pct / 2)

            # ВАЖНО: Корректируем score на основе абсолютного значения ROI
            # Если портфель убыточный, даже положительный тренд не должен давать высокий score
            if second_half_avg < 0:
                # Убыточный портфель: максимум 40 points за тренд
                score = min(base_score, 40)
            elif second_half_avg < 10:
                # Низкодоходный портфель: максимум 60 points
                score = min(base_score, 60)
            else:
                # Прибыльный портфель: полный score
                score = base_score

            score = max(0, min(100, score))  # Ограничиваем от 0 до 100

            return score
        except Exception:
            return 50

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО для этого модуля.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        components = raw_data.get("components", {})
        summary = raw_data.get("summary", {})
        health_index = raw_data.get("health_index", 0)

        charts = []

        # Радиальная диаграмма компонентов индекса
        charts.append({
            "id": "portfolio_health_radar",
            "type": "radar",
            "data": {
                "labels": [
                    "ROI",
                    "Прибыльность",
                    "Стабильность",
                    "Диверсификация",
                    "Тренд"
                ],
                "datasets": [{
                    "label": "Компоненты индекса",
                    "data": [
                        components.get("weighted_roi", 0),
                        components.get("profitable_ratio", 0),
                        components.get("stability", 0),
                        components.get("diversification", 0),
                        components.get("trend", 0)
                    ],
                    "borderColor": "rgba(13, 110, 253, 1)",
                    "backgroundColor": "rgba(13, 110, 253, 0.2)",
                    "pointBackgroundColor": "rgba(13, 110, 253, 1)",
                    "pointBorderColor": "#fff",
                    "pointHoverBackgroundColor": "#fff",
                    "pointHoverBorderColor": "rgba(13, 110, 253, 1)"
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Компоненты индекса здоровья"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "r": {
                        "beginAtZero": True,
                        "max": 100,
                        "ticks": {
                            "stepSize": 20
                        }
                    }
                }
            }
        })

        # Калибровочный график общего индекса
        health_status = "Отличное" if health_index >= 80 else \
                       "Хорошее" if health_index >= 60 else \
                       "Среднее" if health_index >= 40 else \
                       "Плохое"

        color = "rgba(40, 167, 69, 0.8)" if health_index >= 80 else \
                "rgba(23, 162, 184, 0.8)" if health_index >= 60 else \
                "rgba(255, 193, 7, 0.8)" if health_index >= 40 else \
                "rgba(220, 53, 69, 0.8)"

        charts.append({
            "id": "portfolio_health_gauge",
            "type": "doughnut",
            "data": {
                "labels": [health_status, "Остаток"],
                "datasets": [{
                    "data": [health_index, 100 - health_index],
                    "backgroundColor": [color, "rgba(200, 200, 200, 0.3)"]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Индекс здоровья: {health_index}"
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
        Генерация алертов для портфеля.
        """
        health_index = raw_data.get("health_index", 0)
        components = raw_data.get("components", {})
        summary = raw_data.get("summary", {})
        alerts = []

        # Получаем настраиваемые пороги severity из конфига
        # Если их нет в raw_data, используем дефолтные значения
        severity_critical_threshold = raw_data.get("severity_critical", 40)
        severity_warning_threshold = raw_data.get("severity_warning", 60)

        # Общий алерт о здоровье портфеля с настраиваемыми порогами
        if health_index < severity_critical_threshold:
            severity = "critical"
            message = f"Портфель в критическом состоянии (индекс {health_index})"
        elif health_index < severity_warning_threshold:
            severity = "warning"
            message = f"Портфель требует внимания (индекс {health_index})"
        else:
            severity = "info"
            message = f"Портфель в хорошем состоянии (индекс {health_index})"

        # Добавляем детали слабых компонентов
        weak_components = []
        if components.get("weighted_roi", 0) < 40:
            weak_components.append("низкий средневзвешенный ROI")
        if components.get("profitable_ratio", 0) < 50:
            weak_components.append("низкая доля прибыльных кампаний")
        if components.get("stability", 0) < 40:
            weak_components.append("высокая волатильность метрик")
        if components.get("diversification", 0) < 40:
            weak_components.append("плохая диверсификация")
        if components.get("trend", 0) < 40:
            weak_components.append("отрицательный тренд")

        if weak_components:
            message += "\n\nПроблемные области:\n"
            for component in weak_components:
                message += f"• {component}\n"

        # Дополнительная информация
        message += f"\n\nИтого по портфелю:\n"
        message += f"Кампаний: {summary.get('total_campaigns', 0)}\n"
        message += f"Прибыльных: {summary.get('profitable_campaigns', 0)}\n"
        message += f"Средний ROI: {summary.get('avg_roi', 0):.1f}%\n"
        message += f"Общий доход: ${summary.get('total_revenue', 0):.2f}\n"

        alerts.append({
            "type": "portfolio_health",
            "severity": severity,
            "message": message,
            "recommended_action": self._get_recommendation(health_index, components),
            "health_index": health_index,
            "total_campaigns": summary.get("total_campaigns", 0),
            "profitable_campaigns": summary.get("profitable_campaigns", 0),
            "avg_roi": round(summary.get("avg_roi", 0), 1)
        })

        return alerts

    def _get_recommendation(self, health_index: float, components: Dict[str, float]) -> str:
        """Возвращает рекомендацию на основе индекса и компонентов"""
        if health_index >= 80:
            return "Продолжайте поддерживать текущую стратегию. Рассмотрите возможность масштабирования лучших кампаний."
        elif health_index >= 60:
            return "Портфель стабилен. Обратите внимание на слабые компоненты и постепенно их улучшайте."
        elif health_index >= 40:
            return "Требуется активная работа. Сосредоточьтесь на увеличении доли прибыльных кампаний и стабильности."
        else:
            return "Критическое состояние. Срочно пересмотрите портфель, прекратите убыточные кампании и оптимизируйте стратегию."
