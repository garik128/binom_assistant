"""
Модуль оценки рисков портфеля (Risk Assessment)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict
import statistics
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


class RiskAssessment(BaseModule):
    """
    Модуль оценки рисков портфеля (Risk Assessment).

    Идентифицирует и квантифицирует риски портфеля на основе:
    - Риск концентрации (один источник > 50%)
    - Риск волатильности (высокая дисперсия ROI)
    - Риск ликвидности (большие pending апрувы)
    - Операционный риск (зависимость от одной группы)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="risk_assessment",
            name="Оценка рисков",
            category="portfolio",
            description="Выявляет и квантифицирует риски портфеля",
            detailed_description="Модуль анализирует риски портфеля по нескольким категориям: концентрация доходов, волатильность, ликвидность и операционные риски. Помогает управлять портфелем более эффективно. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="medium",
            tags=["portfolio", "risk", "concentration", "volatility", "liquidity"]
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
                "min_leads": 50,  # минимальное количество лидов
                "high_concentration_threshold": 50  # порог высокой концентрации (%)
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
            "high_concentration_threshold": {
                "label": "Порог концентрации (%)",
                "description": "Порог высокой концентрации риска на один источник",
                "type": "number",
                "min": 20,
                "max": 100,
                "default": 50
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ рисков портфеля.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные об оценке рисков
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_cost = config.params.get("min_cost", 1.0)
        min_leads = config.params.get("min_leads", 50)
        high_concentration_threshold = config.params.get("high_concentration_threshold", 50)

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
                CampaignStatsDaily.a_leads,
                CampaignStatsDaily.h_leads
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
                "total_h_leads": 0,
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
                h_leads = float(row.h_leads) if row.h_leads else 0

                campaigns_data[campaign_id]["total_cost"] += cost
                campaigns_data[campaign_id]["total_revenue"] += revenue
                campaigns_data[campaign_id]["total_leads"] += leads
                campaigns_data[campaign_id]["total_a_leads"] += a_leads
                campaigns_data[campaign_id]["total_h_leads"] += h_leads

                if cost > 0:
                    campaigns_data[campaign_id]["days_with_data"] += 1

                campaigns_data[campaign_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads,
                    "h_leads": h_leads
                })

            # Анализ портфеля
            portfolio_campaigns = []
            total_portfolio_cost = 0
            total_portfolio_revenue = 0
            roi_values = []
            source_revenue_shares = {}
            group_performance = defaultdict(lambda: {"cost": 0, "revenue": 0, "count": 0})
            total_h_leads = 0

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                cost = data["total_cost"]
                revenue = data["total_revenue"]
                h_leads = data["total_h_leads"]

                # Пропускаем очень маленькие кампании (шум)
                if cost < min_cost or data["total_leads"] < min_leads:
                    continue

                # ROI расчет
                roi = ((revenue - cost) / cost * 100) if cost > 0 else 0
                roi_values.append(roi)

                total_portfolio_cost += cost
                total_portfolio_revenue += revenue
                total_h_leads += h_leads

                # Накопление данных по группам
                group = data["group"]
                group_performance[group]["cost"] += cost
                group_performance[group]["revenue"] += revenue
                group_performance[group]["count"] += 1

                # Накопление по источникам (по группам для доходов)
                if group not in source_revenue_shares:
                    source_revenue_shares[group] = 0
                source_revenue_shares[group] += revenue

                portfolio_campaigns.append({
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": group,
                    "roi": round(roi, 1),
                    "cost": round(cost, 2),
                    "revenue": round(revenue, 2),
                    "h_leads": int(h_leads)
                })

            # Расчет компонентов риска
            total_campaigns = len(portfolio_campaigns)

            # 1. Риск концентрации (один источник > 50%)
            concentration_risk = self._calculate_concentration_risk(source_revenue_shares, total_portfolio_revenue)

            # 2. Риск волатильности (высокая дисперсия ROI)
            volatility_risk = self._calculate_volatility_risk(roi_values)

            # 3. Риск ликвидности (большие pending апрувы)
            liquidity_risk = self._calculate_liquidity_risk(total_h_leads, total_portfolio_revenue)

            # 4. Операционный риск (зависимость от одной группы)
            operational_risk = self._calculate_operational_risk(group_performance, total_campaigns)

            # Общая оценка риска (среднее значение, низкие значения = низкий риск)
            risk_score = (concentration_risk + volatility_risk + liquidity_risk + operational_risk) / 4

            # Определение уровня риска
            if risk_score < 25:
                risk_level = "low"
            elif risk_score < 50:
                risk_level = "medium"
            elif risk_score < 75:
                risk_level = "high"
            else:
                risk_level = "critical"

            return {
                "risk_score": round(risk_score, 1),
                "risk_level": risk_level,
                "risks": {
                    "concentration_risk": round(concentration_risk, 1),
                    "volatility_risk": round(volatility_risk, 1),
                    "liquidity_risk": round(liquidity_risk, 1),
                    "operational_risk": round(operational_risk, 1)
                },
                "summary": {
                    "total_campaigns": total_campaigns,
                    "total_cost": round(total_portfolio_cost, 2),
                    "total_revenue": round(total_portfolio_revenue, 2),
                    "total_h_leads": int(total_h_leads),
                    "roi_std_dev": round(statistics.stdev(roi_values), 1) if len(roi_values) > 1 else 0,
                    "max_source_revenue_share": round(max(source_revenue_shares.values()) / total_portfolio_revenue * 100, 1) if source_revenue_shares and total_portfolio_revenue > 0 else 0
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                }
            }

    def _calculate_concentration_risk(self, source_revenue_shares: Dict[str, float], total_revenue: float) -> float:
        """
        Рассчитывает риск концентрации (один источник > 50%).

        Риск высок, если один источник доходов генерирует > 50% дохода.

        Args:
            source_revenue_shares: Словарь доходов по источникам
            total_revenue: Общий доход портфеля

        Returns:
            float: Score от 0 до 100 (чем выше, тем больше риск)
        """
        if not source_revenue_shares or total_revenue == 0:
            return 50  # Нейтральное значение

        max_revenue = max(source_revenue_shares.values())
        max_share = (max_revenue / total_revenue) * 100

        # Преобразование доли в score риска
        # < 30% -> score 0 (низкий риск)
        # 50% -> score 50 (средний риск)
        # > 70% -> score 100 (критический риск)
        if max_share <= 30:
            risk = 0
        elif max_share >= 70:
            risk = 100
        else:
            # Линейная интерполяция между 30% и 70%
            risk = ((max_share - 30) / 40) * 100

        return risk

    def _calculate_volatility_risk(self, roi_values: List[float]) -> float:
        """
        Рассчитывает риск волатильности (высокая дисперсия ROI).

        Высокая волатильность = высокий риск.

        Args:
            roi_values: Список значений ROI кампаний

        Returns:
            float: Score от 0 до 100 (чем выше, тем больше риск)
        """
        if len(roi_values) < 2:
            return 50

        try:
            mean_roi = statistics.mean(roi_values)
            stdev_roi = statistics.stdev(roi_values)

            # ИСПРАВЛЕНО: Правильная обработка коэффициента вариации
            # Коэффициент вариации (CV) имеет смысл только при ненулевом среднем
            if abs(mean_roi) > 1.0:  # Порог 1% ROI вместо 0.1%
                # Стандартный CV: std / |mean|
                cv = stdev_roi / abs(mean_roi)
            else:
                # Для околонулевого или отрицательного среднего используем нормализованное стандартное отклонение
                # Нормализуем относительно разумного базового уровня (например, 10% ROI)
                # Это позволяет сравнивать волатильность независимо от среднего значения
                cv = stdev_roi / 10.0 if stdev_roi > 0 else 0

            # Преобразование CV в score риска
            # CV = 0 -> score 0 (низкий риск, стабильно)
            # CV = 0.5 -> score 50 (средний риск)
            # CV = 1.0+ -> score 100 (высокий риск, волатильно)
            risk = min(100, cv * 100)

            return risk
        except Exception:
            return 50

    def _calculate_liquidity_risk(self, total_h_leads: float, total_revenue: float) -> float:
        """
        Рассчитывает риск ликвидности (большие pending апрувы).

        Большое количество неаппрувленных лидов = высокий риск.

        Args:
            total_h_leads: Общее количество pending лидов
            total_revenue: Общий доход портфеля

        Returns:
            float: Score от 0 до 100 (чем выше, тем больше риск)
        """
        if total_revenue <= 0:
            return 50

        # Оцениваем потенциальный доход от pending лидов
        # Предполагаем, что средняя стоимость лида примерно равна (revenue / a_leads)
        # Но так как у нас нет точных данных о конверсии, используем эвристику:
        # Риск высок, если pending лидов много по сравнению с доходом

        # Простая метрика: количество pending лидов как процент от дневного дохода
        pending_ratio = (total_h_leads / max(1, total_revenue)) * 100

        # Преобразование в score риска
        # < 10 pending на $1 дохода -> score 0 (низкий риск)
        # 50 pending на $1 дохода -> score 50 (средний риск)
        # > 100 pending на $1 дохода -> score 100 (высокий риск)
        if pending_ratio <= 10:
            risk = 0
        elif pending_ratio >= 100:
            risk = 100
        else:
            risk = (pending_ratio / 100) * 100

        return risk

    def _calculate_operational_risk(self, group_performance: Dict[str, Dict[str, Any]], total_campaigns: int) -> float:
        """
        Рассчитывает операционный риск (зависимость от одной группы).

        Высокая зависимость от одной группы = высокий риск.

        Args:
            group_performance: Словарь производительности по группам
            total_campaigns: Общее количество кампаний

        Returns:
            float: Score от 0 до 100 (чем выше, тем больше риск)
        """
        if total_campaigns == 0 or len(group_performance) == 0:
            return 50

        # Рассчитываем долю каждой группы по количеству кампаний
        group_campaign_counts = [data["count"] for data in group_performance.values()]
        group_shares = [count / total_campaigns for count in group_campaign_counts]

        # Используем индекс Герфиндаля для измерения концентрации
        # HHI = сумма (доля^2)
        # HHI от 0 (идеальная диверсификация) до 1 (полная концентрация)
        hhi = sum(share ** 2 for share in group_shares)

        # Преобразование HHI в score риска
        # HHI = 0 (максимальная диверсификация) -> score 0 (низкий риск)
        # HHI = 0.5 -> score 50 (средний риск)
        # HHI = 1 (одна группа) -> score 100 (высокий риск)
        risk = hhi * 100

        return risk

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО для этого модуля.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        risks = raw_data.get("risks", {})
        risk_score = raw_data.get("risk_score", 0)

        charts = []

        # Радиальная диаграмма компонентов риска
        charts.append({
            "id": "risk_assessment_radar",
            "type": "radar",
            "data": {
                "labels": [
                    "Концентрация",
                    "Волатильность",
                    "Ликвидность",
                    "Операционный"
                ],
                "datasets": [{
                    "label": "Компоненты риска",
                    "data": [
                        risks.get("concentration_risk", 0),
                        risks.get("volatility_risk", 0),
                        risks.get("liquidity_risk", 0),
                        risks.get("operational_risk", 0)
                    ],
                    "borderColor": "rgba(220, 53, 69, 1)",
                    "backgroundColor": "rgba(220, 53, 69, 0.2)",
                    "pointBackgroundColor": "rgba(220, 53, 69, 1)",
                    "pointBorderColor": "#fff",
                    "pointHoverBackgroundColor": "#fff",
                    "pointHoverBorderColor": "rgba(220, 53, 69, 1)"
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Компоненты оценки рисков"
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

        # Калибровочный график общего риска
        risk_level = "Критический" if risk_score >= 75 else \
                     "Высокий" if risk_score >= 50 else \
                     "Средний" if risk_score >= 25 else \
                     "Низкий"

        color = "rgba(220, 53, 69, 0.8)" if risk_score >= 75 else \
                "rgba(255, 193, 7, 0.8)" if risk_score >= 50 else \
                "rgba(23, 162, 184, 0.8)" if risk_score >= 25 else \
                "rgba(40, 167, 69, 0.8)"

        charts.append({
            "id": "risk_assessment_gauge",
            "type": "doughnut",
            "data": {
                "labels": [risk_level, "Остаток"],
                "datasets": [{
                    "data": [risk_score, 100 - risk_score],
                    "backgroundColor": [color, "rgba(200, 200, 200, 0.3)"]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Оценка риска: {risk_score}"
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
        risk_score = raw_data.get("risk_score", 0)
        risk_level = raw_data.get("risk_level", "medium")
        risks = raw_data.get("risks", {})
        summary = raw_data.get("summary", {})
        alerts = []

        # Общий алерт о риске портфеля
        if risk_level == "low":
            severity = "info"
            message = f"Портфель низкого риска (score {risk_score})"
        elif risk_level == "medium":
            severity = "info"
            message = f"Портфель среднего риска (score {risk_score})"
        elif risk_level == "high":
            severity = "warning"
            message = f"Портфель высокого риска (score {risk_score})"
        else:  # critical
            severity = "critical"
            message = f"Портфель критического риска (score {risk_score})"

        # Добавляем детали высоких рисков
        high_risks = []
        if risks.get("concentration_risk", 0) > 50:
            high_risks.append(f"высокая концентрация доходов ({risks.get('concentration_risk', 0):.1f})")
        if risks.get("volatility_risk", 0) > 50:
            high_risks.append(f"высокая волатильность ROI ({risks.get('volatility_risk', 0):.1f})")
        if risks.get("liquidity_risk", 0) > 50:
            high_risks.append(f"высокий риск ликвидности ({risks.get('liquidity_risk', 0):.1f})")
        if risks.get("operational_risk", 0) > 50:
            high_risks.append(f"операционный риск ({risks.get('operational_risk', 0):.1f})")

        if high_risks:
            message += "\n\nВысокие риски:\n"
            for risk_item in high_risks:
                message += f"• {risk_item}\n"

        # Дополнительная информация
        message += f"\n\nСведения о портфеле:\n"
        message += f"Кампаний: {summary.get('total_campaigns', 0)}\n"
        message += f"Общий доход: ${summary.get('total_revenue', 0):.2f}\n"
        message += f"Pending лидов: {summary.get('total_h_leads', 0)}\n"

        alerts.append({
            "type": "portfolio_risk",
            "severity": severity,
            "message": message,
            "recommended_action": self._get_recommendation(risk_level, risks),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "total_campaigns": summary.get("total_campaigns", 0),
            "total_h_leads": summary.get("total_h_leads", 0)
        })

        return alerts

    def _get_recommendation(self, risk_level: str, risks: Dict[str, float]) -> str:
        """Возвращает рекомендацию на основе уровня риска"""
        if risk_level == "low":
            return "Портфель имеет низкий риск. Продолжайте текущую стратегию управления."
        elif risk_level == "medium":
            return "Портфель имеет средний риск. Рассмотрите диверсификацию и управление volatile кампаниями."
        elif risk_level == "high":
            return "Портфель имеет высокий риск. Срочно увеличьте диверсификацию и снизьте концентрацию."
        else:  # critical
            return "Портфель имеет критический риск. Требуется немедленное действие: реструктурировать портфель, снять высокорисковые кампании."
