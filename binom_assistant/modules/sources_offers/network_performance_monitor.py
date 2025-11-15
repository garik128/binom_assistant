"""
Модуль мониторинга эффективности партнерских сетей (Network Performance Monitor)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager
from collections import defaultdict
import statistics

from storage.database.base import get_session
from storage.database.models import AffiliateNetwork, NetworkStatsDaily
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


class NetworkPerformanceMonitor(BaseModule):
    """
    Модуль мониторинга эффективности партнерских сетей (Network Performance Monitor).

    Анализирует производительность партнерских сетей (affiliate networks):
    - Средний approve rate по сети
    - Средняя задержка апрувов (дней)
    - Количество активных офферов
    - Общий ROI
    - Расчет performance score и статуса
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="network_performance_monitor",
            name="Эффективность сетей",
            category="sources_offers",
            description="Мониторит эффективность партнерских сетей",
            detailed_description="Модуль анализирует производительность партнерских сетей на основе данных из таблиц affiliate_networks и network_stats_daily. Рассчитывает approve rate, средний ROI, количество активных офферов по каждой сети. Помогает выявить самые эффективные и проблемные партнерки для оптимизации. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой).",
            version="1.1.0",
            author="Binom Assistant",
            priority="medium",
            tags=["networks", "approval_rate", "roi", "performance", "sources"]
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
                "days": 14,  # увеличенный период для апрувов
                "min_cost": 1.0,  # минимальный расход для анализа
                "slow_approval_threshold": 7,  # порог медленного апрува (дней)
                "many_campaigns_threshold": 10,  # порог многих офферов в сети
                "severity_low_approve": 20,  # порог для warning severity (низкий approve rate)
                "severity_long_delay": 5  # порог для info severity (долгая задержка апрувов)
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа производительности сетей",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 14
            },
            "min_cost": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход для включения сети в анализ",
                "type": "number",
                "min": 0.1,
                "max": 10000,
                "default": 1.0
            },
            "slow_approval_threshold": {
                "label": "Порог медленного апрува (дней)",
                "description": "Количество дней задержки, после которого апрув считается медленным",
                "type": "number",
                "min": 1,
                "max": 30,
                "default": 7
            },
            "many_campaigns_threshold": {
                "label": "Порог многих офферов",
                "description": "Количество офферов, после которого сеть считается крупной",
                "type": "number",
                "min": 1,
                "max": 100,
                "default": 10
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "approve_rate",
            "metric_label": "Approve Rate",
            "metric_unit": "%",
            "description": "Пороги критичности на основе approve rate и задержки апрувов",
            "thresholds": {
                "severity_low_approve": {
                    "label": "Порог низкого approve rate",
                    "description": "Approve rate ниже этого значения - критично (warning)",
                    "type": "number",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "default": 20
                },
                "severity_long_delay": {
                    "label": "Порог долгой задержки",
                    "description": "Задержка апрувов выше этого значения (дней) - info",
                    "type": "number",
                    "min": 1,
                    "max": 30,
                    "step": 1,
                    "default": 5
                }
            },
            "levels": [
                {"value": "warning", "label": "Предупреждение", "color": "#f59e0b", "condition": "approve_rate < low_approve"},
                {"value": "info", "label": "Инфо", "color": "#3b82f6", "condition": "delay > long_delay"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ эффективности сетей.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о производительности сетей
        """
        # Получение параметров
        days = config.params.get("days", 14)
        min_cost = config.params.get("min_cost", 1.0)
        slow_approval_threshold = config.params.get("slow_approval_threshold", 7)
        many_campaigns_threshold = config.params.get("many_campaigns_threshold", 10)

        # Исключаем сегодняшний день (апрувы приходят с задержкой)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Получаем данные по партнерским сетям с их статистикой
            query = session.query(
                AffiliateNetwork.id,
                AffiliateNetwork.name,
                AffiliateNetwork.status,
                NetworkStatsDaily.date,
                NetworkStatsDaily.cost,
                NetworkStatsDaily.revenue,
                NetworkStatsDaily.leads,
                NetworkStatsDaily.a_leads,
                NetworkStatsDaily.active_offers
            ).join(
                NetworkStatsDaily,
                AffiliateNetwork.id == NetworkStatsDaily.network_id
            ).filter(
                NetworkStatsDaily.date >= date_from
            ).order_by(
                AffiliateNetwork.id,
                NetworkStatsDaily.date
            )

            results = query.all()

            # Группировка по партнерским сетям
            networks_data = defaultdict(lambda: {
                "network_id": None,
                "network_name": None,
                "status": True,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0,
                "active_offers_max": 0,
                "daily_stats": [],
                "days_with_data": 0
            })

            for row in results:
                network_id = row.id
                networks_data[network_id]["network_id"] = row.id
                networks_data[network_id]["network_name"] = row.name
                networks_data[network_id]["status"] = row.status

                cost = float(row.cost) if row.cost else 0
                revenue = float(row.revenue) if row.revenue else 0
                leads = float(row.leads) if row.leads else 0
                a_leads = float(row.a_leads) if row.a_leads else 0
                active_offers = int(row.active_offers) if row.active_offers else 0

                networks_data[network_id]["total_cost"] += cost
                networks_data[network_id]["total_revenue"] += revenue
                networks_data[network_id]["total_leads"] += leads
                networks_data[network_id]["total_a_leads"] += a_leads

                # Максимальное количество активных офферов за период
                if active_offers > networks_data[network_id]["active_offers_max"]:
                    networks_data[network_id]["active_offers_max"] = active_offers

                if cost > 0:
                    networks_data[network_id]["days_with_data"] += 1

                networks_data[network_id]["daily_stats"].append({
                    "date": row.date,
                    "cost": cost,
                    "revenue": revenue,
                    "leads": leads,
                    "a_leads": a_leads,
                    "active_offers": active_offers
                })

            # Расчет метрик по сетям
            networks_list = []

            for network_id, network_info in networks_data.items():
                # Пропускаем сети без данных
                if network_info["days_with_data"] == 0:
                    continue

                # Пропускаем очень маленькие сети (шум)
                if network_info["total_cost"] < 1:
                    continue

                # Средний approve rate
                total_leads = network_info["total_leads"]
                total_approved = network_info["total_a_leads"]

                if total_leads > 0:
                    avg_approve_rate = (total_approved / total_leads) * 100
                else:
                    avg_approve_rate = 0.0

                # Средняя задержка апрувов (в часах, рассчитывается на основе дневных данных)
                approval_delays = []
                daily_stats = network_info["daily_stats"]
                delays = self._calculate_approval_delays(daily_stats)
                approval_delays.extend(delays)

                if approval_delays:
                    avg_approval_delay = statistics.mean(approval_delays)
                else:
                    avg_approval_delay = 0.0

                # Общий ROI
                total_cost = network_info["total_cost"]
                total_revenue = network_info["total_revenue"]

                if total_cost > 0:
                    total_roi = ((total_revenue - total_cost) / total_cost) * 100
                else:
                    total_roi = 0.0

                # Расчет performance score на основе метрик
                performance_score = self._calculate_performance_score(
                    avg_approve_rate,
                    avg_approval_delay,
                    total_roi,
                    network_info["active_offers_max"]
                )

                # Определение статуса
                status = self._get_status(performance_score, avg_approve_rate, total_roi)

                networks_list.append({
                    "network": network_info["network_name"],
                    "network_id": network_id,
                    "avg_approve_rate": round(avg_approve_rate, 1),
                    "avg_approval_delay": round(avg_approval_delay, 1),
                    "active_offers": network_info["active_offers_max"],  # активные офферы
                    "total_roi": round(total_roi, 1),
                    "performance_score": round(performance_score, 1),
                    "status": status,
                    "total_cost": round(total_cost, 2),
                    "total_revenue": round(total_revenue, 2)
                })

            # Сортировка по performance_score (убывающий порядок)
            networks_list.sort(key=lambda x: x["performance_score"], reverse=True)

            return {
                "networks": networks_list,
                "summary": {
                    "total_networks": len(networks_list),
                    "avg_performance_score": round(
                        statistics.mean([n["performance_score"] for n in networks_list]), 1
                    ) if networks_list else 0,
                    "best_network": networks_list[0]["network"] if networks_list else None,
                    "worst_network": networks_list[-1]["network"] if networks_list else None
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "thresholds": {
                    "severity_low_approve": config.params.get("severity_low_approve", 20),
                    "severity_long_delay": config.params.get("severity_long_delay", 5)
                }
            }

    def _calculate_approval_delays(self, daily_stats: List[Dict[str, Any]]) -> List[float]:
        """
        Рассчитывает задержку апрувов на основе дневных данных.

        Args:
            daily_stats: Список дневных статистик

        Returns:
            List[float]: Список задержек в днях
        """
        delays = []

        # Сортируем по дате
        sorted_stats = sorted(daily_stats, key=lambda x: x["date"])

        # Если есть лиды, но нет апрувов на той же день, считаем задержку
        for i, stat in enumerate(sorted_stats):
            leads = stat["leads"]
            approved = stat["a_leads"]

            # Если есть лиды, но нет апрувов в этот день
            if leads > 0 and approved == 0:
                # Ищем день когда появились апрувы
                for j in range(i + 1, min(i + 7, len(sorted_stats))):
                    if sorted_stats[j]["a_leads"] > 0:
                        delay_days = (sorted_stats[j]["date"] - stat["date"]).days
                        if delay_days > 0:
                            delays.append(float(delay_days))
                        break

        return delays

    def _calculate_performance_score(
        self,
        approve_rate: float,
        approval_delay: float,
        roi: float,
        campaigns_count: int
    ) -> float:
        """
        Рассчитывает общий performance score сети (0-100).

        Args:
            approve_rate: Процент апрувов (0-100)
            approval_delay: Задержка апрувов в днях
            roi: ROI в процентах
            campaigns_count: Количество активных офферов

        Returns:
            float: Score от 0 до 100
        """
        # Компонент 1: Approve rate (вес 40%)
        # 50% approve rate -> 50 баллов
        # 100% approve rate -> 100 баллов
        approve_score = min(100, approve_rate)
        approve_component = approve_score * 0.40

        # Компонент 2: Задержка апрувов (вес 25%)
        # 0 дней -> 100 баллов
        # 3 дня -> 50 баллов
        # 7 дней -> 0 баллов
        if approval_delay <= 0:
            delay_score = 100
        elif approval_delay >= 7:
            delay_score = 0
        else:
            delay_score = max(0, 100 - (approval_delay / 7 * 100))
        delay_component = delay_score * 0.25

        # Компонент 3: ROI (вес 25%)
        # -100% ROI -> score 0
        # 0% ROI -> score 50
        # 100% ROI -> score 100
        roi_score = max(0, min(100, 50 + roi / 2))
        roi_component = roi_score * 0.25

        # Компонент 4: Количество офферов (вес 10%)
        # Бонус за диверсификацию в сети
        if campaigns_count >= 10:
            volume_score = 100
        elif campaigns_count >= 5:
            volume_score = 75
        elif campaigns_count >= 3:
            volume_score = 50
        else:
            volume_score = 25
        volume_component = volume_score * 0.10

        total_score = approve_component + delay_component + roi_component + volume_component

        return total_score

    def _get_status(self, score: float, approve_rate: float, roi: float) -> str:
        """
        Определяет статус сети.

        Args:
            score: Performance score
            approve_rate: Процент апрувов
            roi: ROI в процентах

        Returns:
            str: Статус (excellent/good/average/poor)
        """
        if score >= 80 and approve_rate >= 50 and roi > 0:
            return "excellent"
        elif score >= 60 and approve_rate >= 30:
            return "good"
        elif score >= 40:
            return "average"
        else:
            return "poor"

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО для этого модуля.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        networks = raw_data.get("networks", [])

        if not networks:
            return []

        charts = []

        # График 1: Сравнение метрик по сетям (столбчатая диаграмма)
        network_names = [n["network"] for n in networks]
        approve_rates = [n["avg_approve_rate"] for n in networks]
        rois = [max(-100, n["total_roi"]) for n in networks]  # Ограничиваем для визуализации
        performance_scores = [n["performance_score"] for n in networks]

        charts.append({
            "id": "network_performance_comparison",
            "type": "bar",
            "data": {
                "labels": network_names,
                "datasets": [
                    {
                        "label": "Approve Rate (%)",
                        "data": approve_rates,
                        "backgroundColor": "rgba(13, 110, 253, 0.7)",
                        "yAxisID": "y"
                    },
                    {
                        "label": "ROI (%)",
                        "data": rois,
                        "backgroundColor": "rgba(40, 167, 69, 0.7)",
                        "yAxisID": "y1"
                    }
                ]
            },
            "options": {
                "responsive": True,
                "interaction": {
                    "mode": "index",
                    "intersect": False
                },
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Сравнение метрик по сетям"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "y": {
                        "type": "linear",
                        "display": True,
                        "position": "left",
                        "title": {
                            "display": True,
                            "text": "Approve Rate (%)"
                        }
                    },
                    "y1": {
                        "type": "linear",
                        "display": True,
                        "position": "right",
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        },
                        "grid": {
                            "drawOnChartArea": False
                        }
                    }
                }
            }
        })

        # График 2: Performance Score по сетям (горизонтальная полоса)
        charts.append({
            "id": "network_performance_score",
            "type": "bar",
            "data": {
                "labels": network_names,
                "datasets": [{
                    "label": "Performance Score",
                    "data": performance_scores,
                    "backgroundColor": [
                        "rgba(40, 167, 69, 0.7)" if score >= 80 else
                        "rgba(23, 162, 184, 0.7)" if score >= 60 else
                        "rgba(255, 193, 7, 0.7)" if score >= 40 else
                        "rgba(220, 53, 69, 0.7)"
                        for score in performance_scores
                    ]
                }]
            },
            "options": {
                "responsive": True,
                "indexAxis": "y",
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Performance Score по сетям"
                    },
                    "legend": {
                        "position": "bottom"
                    }
                },
                "scales": {
                    "x": {
                        "beginAtZero": True,
                        "max": 100,
                        "ticks": {
                            "stepSize": 20
                        }
                    }
                }
            }
        })

        # График 3: Распределение активных офферов по сетям
        active_offers = [n["active_offers"] for n in networks]

        # Создаем график только если есть данные с офферами
        if active_offers and sum(active_offers) > 0:
            charts.append({
                "id": "network_offers_distribution",
                "type": "doughnut",
                "data": {
                    "labels": network_names,
                    "datasets": [{
                        "data": active_offers,
                        "backgroundColor": [
                            "rgba(13, 110, 253, 0.7)",
                            "rgba(40, 167, 69, 0.7)",
                            "rgba(23, 162, 184, 0.7)",
                            "rgba(255, 193, 7, 0.7)",
                            "rgba(220, 53, 69, 0.7)",
                            "rgba(111, 66, 193, 0.7)",
                            "rgba(52, 211, 153, 0.7)",
                            "rgba(245, 158, 11, 0.7)"
                        ][:len(network_names)]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение активных офферов по сетям"
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
        Генерация алертов для сетей.
        """
        networks = raw_data.get("networks", [])
        summary = raw_data.get("summary", {})
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        if not networks:
            return alerts

        # Получаем настраиваемые пороги severity
        severity_low_approve = thresholds.get("severity_low_approve", 20)
        severity_long_delay = thresholds.get("severity_long_delay", 5)

        # Алерт о лучшей сети
        best_network = networks[0]
        if best_network["status"] == "excellent":
            alerts.append({
                "type": "network_excellent",
                "severity": "info",
                "message": f"Сеть '{best_network['network']}' показывает отличные результаты (score: {best_network['performance_score']}, approve rate: {best_network['avg_approve_rate']}%)",
                "network": best_network["network"],
                "performance_score": best_network["performance_score"]
            })

        # Алерт о худшей сети
        if len(networks) > 1:
            worst_network = networks[-1]
            if worst_network["status"] == "poor":
                alerts.append({
                    "type": "network_poor",
                    "severity": "warning",
                    "message": f"Сеть '{worst_network['network']}' требует внимания (score: {worst_network['performance_score']}, approve rate: {worst_network['avg_approve_rate']}%)",
                    "network": worst_network["network"],
                    "performance_score": worst_network["performance_score"]
                })

        # Алерты о низком approve rate с настраиваемым порогом
        for network in networks:
            if network["avg_approve_rate"] < severity_low_approve and network["active_offers"] >= 3:
                alerts.append({
                    "type": "network_low_approve_rate",
                    "severity": "warning",
                    "message": f"Сеть '{network['network']}': очень низкий approve rate ({network['avg_approve_rate']}% < {severity_low_approve}%)",
                    "network": network["network"],
                    "approve_rate": network["avg_approve_rate"],
                    "threshold": severity_low_approve
                })

        # Алерты о долгой задержке апрувов с настраиваемым порогом
        for network in networks:
            if network["avg_approval_delay"] > severity_long_delay:
                alerts.append({
                    "type": "network_long_approval_delay",
                    "severity": "info",
                    "message": f"Сеть '{network['network']}': долгая задержка апрувов ({network['avg_approval_delay']} дней > {severity_long_delay})",
                    "network": network["network"],
                    "approval_delay": network["avg_approval_delay"],
                    "threshold": severity_long_delay
                })

        return alerts
