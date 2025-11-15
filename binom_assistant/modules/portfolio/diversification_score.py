"""
Модуль расчета индекса диверсификации портфеля (Diversification Score)
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


class DiversificationScore(BaseModule):
    """
    Модуль расчета индекса диверсификации портфеля (Diversification Score).

    Оценивает диверсификацию рисков портфеля на основе:
    - Индекса Херфиндаля-Хиршмана (HHI) для источников
    - Распределения по группам (не более 30% на одну)
    - Баланса CPL vs CPA кампаний
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="diversification_score",
            name="Диверсификация",
            category="portfolio",
            description="Оценивает диверсификацию рисков портфеля",
            detailed_description="Модуль анализирует распределение кампаний по источникам и группам, рассчитывает индекс Херфиндаля-Хиршмана и баланс CPL/CPA кампаний для оценки риска концентрации.",
            version="1.1.0",
            author="Binom Assistant",
            priority="medium",
            tags=["portfolio", "diversification", "risk", "hhi", "balance"]
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
                "max_single_source_share": 30,  # макс доля одного источника (%)
                "max_single_group_share": 30,  # макс доля одной группы (%)
                "hhi_threshold": 0.25,  # порог HHI для высокой концентрации
                "critical_source_share": 40  # критическая доля источника (%)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа диверсификации",
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
            "max_single_source_share": {
                "label": "Макс. доля источника (%)",
                "description": "Максимальная безопасная доля одного источника в портфеле",
                "type": "number",
                "min": 10,
                "max": 100,
                "default": 30
            },
            "max_single_group_share": {
                "label": "Макс. доля группы (%)",
                "description": "Максимальная безопасная доля одной группы в портфеле",
                "type": "number",
                "min": 10,
                "max": 100,
                "default": 30
            },
            "hhi_threshold": {
                "label": "Порог HHI",
                "description": "Индекс Херфиндаля-Хиршмана: порог высокой концентрации (0-1)",
                "type": "number",
                "min": 0.1,
                "max": 1.0,
                "default": 0.25
            },
            "critical_source_share": {
                "label": "Критическая доля источника (%)",
                "description": "Критически высокая доля одного источника",
                "type": "number",
                "min": 20,
                "max": 100,
                "default": 40
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ диверсификации портфеля.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о диверсификации
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_cost = config.params.get("min_cost", 1.0)
        min_leads = config.params.get("min_leads", 50)
        max_single_source_share = config.params.get("max_single_source_share", 30)
        max_single_group_share = config.params.get("max_single_group_share", 30)
        hhi_threshold = config.params.get("hhi_threshold", 0.25)
        critical_source_share = config.params.get("critical_source_share", 40)

        date_from = datetime.now().date() - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # ИСПРАВЛЕНО: Запрашиваем ts_name как источник трафика
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                Campaign.ts_name,  # ИСПРАВЛЕНО: используем ts_name вместо дублирования group_name
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
                "source": None,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "days_with_data": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"
                campaigns_data[campaign_id]["source"] = row.ts_name or "Неизвестен"  # ИСПРАВЛЕНО: используем ts_name

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

            # Фильтрация и анализ
            portfolio_campaigns = []
            source_distribution = defaultdict(float)  # расход по источникам
            group_distribution = defaultdict(float)   # расход по группам
            campaign_types = {"cpl": 0, "cpa": 0}
            total_portfolio_cost = 0
            total_portfolio_revenue = 0

            for campaign_id, data in campaigns_data.items():
                # Пропускаем кампании без данных
                if data["days_with_data"] == 0:
                    continue

                cost = data["total_cost"]
                revenue = data["total_revenue"]
                leads = data["total_leads"]
                a_leads = data["total_a_leads"]

                # Пропускаем очень маленькие кампании (шум)
                if cost < min_cost or leads < min_leads:
                    continue

                total_portfolio_cost += cost
                total_portfolio_revenue += revenue

                # Распределение по источникам
                source = data["source"]
                source_distribution[source] += cost

                # Распределение по группам
                group = data["group"]
                group_distribution[group] += cost

                # Определение типа кампании (CPL vs CPA)
                if a_leads > 0 and revenue > 0:
                    campaign_types["cpa"] += 1
                elif leads > 0 and revenue > 0 and a_leads == 0:
                    campaign_types["cpl"] += 1

                portfolio_campaigns.append({
                    "campaign_id": campaign_id,
                    "name": data["name"],
                    "source": source,
                    "group": group,
                    "cost": round(cost, 2),
                    "revenue": round(revenue, 2),
                    "type": "CPA" if (a_leads > 0 and revenue > 0) else "CPL" if (leads > 0 and revenue > 0) else "Unknown"
                })

            # Расчет диверсификации
            if total_portfolio_cost == 0:
                return self._get_empty_result(days)

            # 1. Индекс Херфиндаля-Хиршмана (HHI) для источников
            hhi_sources = self._calculate_hhi(source_distribution, total_portfolio_cost)

            # 2. Top source share (доля самого большого источника)
            top_source_share = max(source_distribution.values()) / total_portfolio_cost * 100 if source_distribution else 0

            # 3. Top group share (доля самой большой группы)
            top_group_share = max(group_distribution.values()) / total_portfolio_cost * 100 if group_distribution else 0

            # 4. CPL vs CPA баланс
            total_types = campaign_types["cpl"] + campaign_types["cpa"]
            cpl_cpa_balance = (campaign_types["cpa"] / total_types * 100) if total_types > 0 else 50

            # 5. Расчет общего score диверсификации
            diversification_score = self._calculate_diversification_score(
                hhi_sources,
                top_source_share,
                top_group_share,
                cpl_cpa_balance,
                max_single_source_share,
                max_single_group_share
            )

            # 6. Определение уровня риска
            risk_level = self._determine_risk_level(
                hhi_sources,
                top_source_share,
                top_group_share,
                cpl_cpa_balance,
                hhi_threshold,
                critical_source_share
            )

            return {
                "diversification_score": round(diversification_score, 1),
                "hhi_sources": round(hhi_sources, 4),
                "top_source_share": round(top_source_share, 1),
                "top_group_share": round(top_group_share, 1),
                "cpl_cpa_balance": round(cpl_cpa_balance, 1),
                "risk_level": risk_level,
                "summary": {
                    "total_campaigns": len(portfolio_campaigns),
                    "unique_sources": len(source_distribution),
                    "unique_groups": len(group_distribution),
                    "cpa_campaigns": campaign_types["cpa"],
                    "cpl_campaigns": campaign_types["cpl"],
                    "total_cost": round(total_portfolio_cost, 2),
                    "total_revenue": round(total_portfolio_revenue, 2)
                },
                "distributions": {
                    "sources": {k: round(v / total_portfolio_cost * 100, 1) for k, v in sorted(source_distribution.items(), key=lambda x: x[1], reverse=True)[:5]},
                    "groups": {k: round(v / total_portfolio_cost * 100, 1) for k, v in sorted(group_distribution.items(), key=lambda x: x[1], reverse=True)[:5]}
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                }
            }

    def _get_empty_result(self, days: int) -> Dict[str, Any]:
        """Возвращает пустой результат когда нет данных"""
        return {
            "diversification_score": 50.0,
            "hhi_sources": 0.0,
            "top_source_share": 0.0,
            "top_group_share": 0.0,
            "cpl_cpa_balance": 50.0,
            "risk_level": "unknown",
            "summary": {
                "total_campaigns": 0,
                "unique_sources": 0,
                "unique_groups": 0,
                "cpa_campaigns": 0,
                "cpl_campaigns": 0,
                "total_cost": 0.0,
                "total_revenue": 0.0
            },
            "distributions": {
                "sources": {},
                "groups": {}
            },
            "period": {
                "days": days,
                "date_from": (datetime.now().date() - timedelta(days=days - 1)).isoformat(),
                "date_to": datetime.now().date().isoformat()
            }
        }

    def _calculate_hhi(self, distribution: Dict[str, float], total: float) -> float:
        """
        Расчет индекса Херфиндаля-Хиршмана (HHI).

        HHI = сумма (доля_i ^ 2)
        HHI от 0 (идеальная диверсификация) до 1 (полная концентрация)

        Args:
            distribution: Словарь распределения по категориям
            total: Общая сумма

        Returns:
            float: HHI индекс от 0 до 1
        """
        if total == 0:
            return 0.5

        hhi = sum((value / total) ** 2 for value in distribution.values())
        return min(hhi, 1.0)  # HHI не может быть больше 1

    def _calculate_diversification_score(
        self,
        hhi_sources: float,
        top_source_share: float,
        top_group_share: float,
        cpl_cpa_balance: float,
        max_single_source_share: float = 30,
        max_single_group_share: float = 30
    ) -> float:
        """
        Расчет общего score диверсификации (0-100).

        Комбинирует несколько метрик:
        - HHI источников (30%): низкий HHI лучше
        - Доля топ источника (25%): низкая доля лучше
        - Доля топ группы (25%): низкая доля лучше
        - CPL/CPA баланс (20%): баланс ~ 50% лучше

        Args:
            hhi_sources: HHI индекс источников (0-1)
            top_source_share: Доля топ источника (0-100%)
            top_group_share: Доля топ группы (0-100%)
            cpl_cpa_balance: % CPA кампаний (0-100%)
            max_single_source_share: Порог безопасной доли источника (%)
            max_single_group_share: Порог безопасной доли группы (%)

        Returns:
            float: Score от 0 до 100
        """
        # HHI score: (1 - hhi) * 100
        hhi_score = (1 - hhi_sources) * 100

        # Top source score: (1 - share/100) * 100, но с штрафом если > порога
        if top_source_share <= max_single_source_share:
            top_source_score = 100 - (top_source_share / max_single_source_share * 50)
        else:
            remaining = 100 - max_single_source_share
            top_source_score = max(0, 50 - ((top_source_share - max_single_source_share) / remaining * 50))

        # Top group score: похоже как top source
        if top_group_share <= max_single_group_share:
            top_group_score = 100 - (top_group_share / max_single_group_share * 50)
        else:
            remaining = 100 - max_single_group_share
            top_group_score = max(0, 50 - ((top_group_share - max_single_group_share) / remaining * 50))

        # Balance score: максимум в районе 50%
        balance_diff = abs(cpl_cpa_balance - 50)
        balance_score = max(0, 100 - (balance_diff / 50 * 100))

        # Комбинированный score
        diversification_score = (
            hhi_score * 0.30 +
            top_source_score * 0.25 +
            top_group_score * 0.25 +
            balance_score * 0.20
        )

        return max(0, min(100, diversification_score))

    def _determine_risk_level(
        self,
        hhi_sources: float,
        top_source_share: float,
        top_group_share: float,
        cpl_cpa_balance: float,
        hhi_threshold: float = 0.25,
        critical_source_share: float = 40
    ) -> str:
        """
        Определение уровня риска на основе метрик диверсификации.

        Args:
            hhi_sources: HHI индекс источников
            top_source_share: Доля топ источника (%)
            top_group_share: Доля топ группы (%)
            cpl_cpa_balance: % CPA кампаний
            hhi_threshold: Порог HHI для высокой концентрации
            critical_source_share: Критическая доля источника (%)

        Returns:
            str: "low", "medium" или "high"
        """
        risk_factors = 0

        # HHI риск
        if hhi_sources > hhi_threshold:
            risk_factors += 1

        # Top source риск
        if top_source_share > critical_source_share:
            risk_factors += 2

        # Top group риск
        if top_group_share > critical_source_share:
            risk_factors += 2
        elif top_group_share > 30:
            risk_factors += 1

        # Balance риск
        balance_diff = abs(cpl_cpa_balance - 50)
        if balance_diff > 40:
            risk_factors += 1

        if risk_factors >= 4:
            return "high"
        elif risk_factors >= 2:
            return "medium"
        else:
            return "low"

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций по улучшению диверсификации.
        """
        recommendations = []

        diversification_score = raw_data.get("diversification_score", 50)
        hhi_sources = raw_data.get("hhi_sources", 0.5)
        top_source_share = raw_data.get("top_source_share", 0)
        top_group_share = raw_data.get("top_group_share", 0)
        cpl_cpa_balance = raw_data.get("cpl_cpa_balance", 50)
        risk_level = raw_data.get("risk_level", "unknown")

        if diversification_score < 50:
            if top_source_share > 40:
                recommendations.append(
                    f"Один источник трафика занимает {top_source_share:.1f}% расходов. "
                    f"Рассмотрите добавление новых источников для снижения риска."
                )

            if top_group_share > 40:
                recommendations.append(
                    f"Одна группа кампаний занимает {top_group_share:.1f}% расходов. "
                    f"Распределите бюджет между другими группами."
                )

            if hhi_sources > 0.25:
                recommendations.append(
                    f"Высокая концентрация расходов по источникам (HHI = {hhi_sources:.3f}). "
                    f"Добавьте новые источники для диверсификации."
                )

        balance_diff = abs(cpl_cpa_balance - 50)
        if balance_diff > 40:
            if cpl_cpa_balance > 70:
                recommendations.append(
                    f"Портфель имеет дисбаланс в сторону CPA кампаний ({cpl_cpa_balance:.1f}%). "
                    f"Рассмотрите добавление CPL кампаний для баланса."
                )
            else:
                recommendations.append(
                    f"Портфель имеет дисбаланс в сторону CPL кампаний ({100 - cpl_cpa_balance:.1f}%). "
                    f"Рассмотрите добавление CPA кампаний для баланса."
                )

        if not recommendations:
            recommendations.append("Портфель хорошо диверсифицирован. Продолжайте поддерживать текущий баланс.")

        return recommendations

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        charts = []

        diversification_score = raw_data.get("diversification_score", 0)
        hhi_sources = raw_data.get("hhi_sources", 0)
        top_source_share = raw_data.get("top_source_share", 0)
        top_group_share = raw_data.get("top_group_share", 0)
        cpl_cpa_balance = raw_data.get("cpl_cpa_balance", 50)
        distributions = raw_data.get("distributions", {})
        summary = raw_data.get("summary", {})

        # График 1: Диаграмма основного score диверсификации
        color = "rgba(40, 167, 69, 0.8)" if diversification_score >= 70 else \
                "rgba(23, 162, 184, 0.8)" if diversification_score >= 50 else \
                "rgba(255, 193, 7, 0.8)" if diversification_score >= 30 else \
                "rgba(220, 53, 69, 0.8)"

        status = "Отличная" if diversification_score >= 70 else \
                 "Хорошая" if diversification_score >= 50 else \
                 "Средняя" if diversification_score >= 30 else \
                 "Низкая"

        charts.append({
            "id": "diversification_gauge",
            "type": "doughnut",
            "data": {
                "labels": [status, "Остаток"],
                "datasets": [{
                    "data": [diversification_score, 100 - diversification_score],
                    "backgroundColor": [color, "rgba(200, 200, 200, 0.3)"]
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": f"Индекс диверсификации: {diversification_score:.1f}"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                }
            }
        })

        # График 2: Распределение по источникам
        sources = distributions.get("sources", {})
        if sources:
            charts.append({
                "id": "diversification_sources",
                "type": "doughnut",
                "data": {
                    "labels": list(sources.keys()),
                    "datasets": [{
                        "data": list(sources.values()),
                        "backgroundColor": [
                            "rgba(13, 110, 253, 0.8)",
                            "rgba(40, 167, 69, 0.8)",
                            "rgba(23, 162, 184, 0.8)",
                            "rgba(255, 193, 7, 0.8)",
                            "rgba(220, 53, 69, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по источникам (%)"
                        },
                        "legend": {
                            "position": "bottom"
                        }
                    }
                }
            })

        # График 3: Распределение по группам
        groups = distributions.get("groups", {})
        if groups:
            charts.append({
                "id": "diversification_groups",
                "type": "doughnut",
                "data": {
                    "labels": list(groups.keys()),
                    "datasets": [{
                        "data": list(groups.values()),
                        "backgroundColor": [
                            "rgba(111, 66, 193, 0.8)",
                            "rgba(232, 62, 140, 0.8)",
                            "rgba(255, 111, 97, 0.8)",
                            "rgba(255, 157, 77, 0.8)",
                            "rgba(255, 193, 7, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по группам (%)"
                        },
                        "legend": {
                            "position": "bottom"
                        }
                    }
                }
            })

        # График 4: CPL vs CPA баланс
        cpa_count = summary.get("cpa_campaigns", 0)
        cpl_count = summary.get("cpl_campaigns", 0)
        if cpa_count + cpl_count > 0:
            charts.append({
                "id": "diversification_cpl_cpa",
                "type": "doughnut",
                "data": {
                    "labels": ["CPA", "CPL"],
                    "datasets": [{
                        "data": [cpl_cpa_balance, 100 - cpl_cpa_balance],
                        "backgroundColor": ["rgba(13, 110, 253, 0.8)", "rgba(40, 167, 69, 0.8)"]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": f"Баланс типов кампаний (CPA: {cpl_cpa_balance:.1f}%)"
                        },
                        "legend": {
                            "position": "bottom"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов по диверсификации.
        """
        alerts = []

        diversification_score = raw_data.get("diversification_score", 50)
        risk_level = raw_data.get("risk_level", "unknown")
        top_source_share = raw_data.get("top_source_share", 0)
        top_group_share = raw_data.get("top_group_share", 0)
        hhi_sources = raw_data.get("hhi_sources", 0.5)
        summary = raw_data.get("summary", {})

        # Основной алерт по диверсификации
        if risk_level == "high":
            severity = "critical"
            message = f"Портфель имеет высокий риск концентрации! Индекс диверсификации: {diversification_score:.1f}"
        elif risk_level == "medium":
            severity = "warning"
            message = f"Портфель требует улучшения диверсификации. Индекс диверсификации: {diversification_score:.1f}"
        else:
            severity = "info"
            message = f"Портфель хорошо диверсифицирован. Индекс диверсификации: {diversification_score:.1f}"

        # Добавляем детали
        message += "\n\n"
        message += f"HHI источников: {hhi_sources:.4f}\n"
        message += f"Доля топ источника: {top_source_share:.1f}%\n"
        message += f"Доля топ группы: {top_group_share:.1f}%\n"
        message += f"Уникальных источников: {summary.get('unique_sources', 0)}\n"
        message += f"Уникальных групп: {summary.get('unique_groups', 0)}\n"

        alerts.append({
            "type": "diversification",
            "severity": severity,
            "message": message,
            "diversification_score": diversification_score,
            "risk_level": risk_level,
            "hhi_sources": hhi_sources,
            "top_source_share": top_source_share,
            "top_group_share": top_group_share
        })

        return alerts
