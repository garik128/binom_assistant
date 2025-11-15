"""
Модуль умного объединения кампаний (Smart Consolidator)
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


class SmartConsolidator(BaseModule):
    """
    Умное объединение похожих малобюджетных кампаний.

    Группирует кампании с похожими характеристиками и малым бюджетом для совместного анализа.
    Позволяет найти паттерны в "длинном хвосте".

    Критерии консолидации:
    - Кластеризация по ROI, CR, источнику
    - Объединение кампаний с расходом < max_daily_spend (по умолчанию $2/день)
    - Минимум min_campaigns_per_cluster кампаний в кластере (по умолчанию 3)
    - Схожесть метрик > similarity_threshold (по умолчанию 80%, косинусное расстояние)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="smart_consolidator",
            name="Умное объединение",
            category="segmentation",
            description="Объединение похожих малобюджетных кампаний",
            detailed_description="Группирует кампании с похожими характеристиками и малым бюджетом для совместного анализа. Позволяет найти паттерны в длинном хвосте малобюджетных кампаний.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["segmentation", "clustering", "consolidation", "analysis"]
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
                "max_daily_spend": 2.0,  # максимальный расход для малобюджетных кампаний ($)
                "min_campaigns_per_cluster": 3,  # минимум кампаний в кластере
                "similarity_threshold": 0.8,  # порог схожести (косинусное расстояние)
                "min_total_clicks": 50  # минимум кликов за период
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа кампаний",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "max_daily_spend": {
                "label": "Макс. расход в день ($)",
                "description": "Максимальный средний расход для малобюджетных кампаний",
                "type": "number",
                "min": 1,
                "max": 10000,
                "default": 2.0
            },
            "min_campaigns_per_cluster": {
                "label": "Минимум кампаний в кластере",
                "description": "Минимальное количество кампаний для формирования кластера",
                "type": "number",
                "min": 2,
                "max": 10,
                "default": 3
            },
            "similarity_threshold": {
                "label": "Порог схожести",
                "description": "Минимальная схожесть метрик для объединения (0.8 = 80%)",
                "type": "number",
                "min": 0.5,
                "max": 1.0,
                "default": 0.8
            },
            "min_total_clicks": {
                "label": "Минимум кликов",
                "description": "Минимальное количество кликов за период для включения в анализ",
                "type": "number",
                "min": 10,
                "max": 10000,
                "default": 50
            }
        }

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Вычисляет косинусное расстояние между двумя векторами.
        Возвращает значение от 0 до 1, где 1 - полностью схожие.
        """
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def _normalize_value(self, value: float, min_val: float, max_val: float) -> float:
        """Нормализация значения в диапазон [0, 1]"""
        if max_val == min_val:
            return 0.5
        return (value - min_val) / (max_val - min_val)

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ и группировка похожих малобюджетных кампаний.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кластерах кампаний
        """
        # Получение параметров
        days = config.params.get("days", 7)
        max_daily_spend = config.params.get("max_daily_spend", 2.0)
        min_campaigns_per_cluster = config.params.get("min_campaigns_per_cluster", 3)
        similarity_threshold = config.params.get("similarity_threshold", 0.8)
        min_total_clicks = config.params.get("min_total_clicks", 50)

        # Период анализа
        date_from = datetime.now().date() - timedelta(days=days - 1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем все кампании с данными за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.clicks,
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
                "total_clicks": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "total_a_leads": 0
            })

            for row in results:
                campaign_id = row.internal_id
                campaigns_data[campaign_id]["binom_id"] = row.binom_id
                campaigns_data[campaign_id]["name"] = row.current_name
                campaigns_data[campaign_id]["group"] = row.group_name or "Без группы"

                campaigns_data[campaign_id]["total_clicks"] += row.clicks or 0
                campaigns_data[campaign_id]["total_cost"] += float(row.cost) if row.cost else 0
                campaigns_data[campaign_id]["total_revenue"] += float(row.revenue) if row.revenue else 0
                campaigns_data[campaign_id]["total_leads"] += row.leads or 0
                campaigns_data[campaign_id]["total_a_leads"] += row.a_leads or 0

            # Фильтрация и подготовка малобюджетных кампаний
            small_campaigns = []
            all_rois = []
            all_crs = []
            all_costs = []

            for campaign_id, data in campaigns_data.items():
                avg_daily_spend = data["total_cost"] / days

                # Фильтры
                if avg_daily_spend > max_daily_spend:
                    continue
                if data["total_clicks"] < min_total_clicks:
                    continue
                if data["total_cost"] == 0:
                    continue

                # Расчет метрик
                roi = ((data["total_revenue"] - data["total_cost"]) / data["total_cost"] * 100) if data["total_cost"] > 0 else -100
                cr = (data["total_leads"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0

                campaign_info = {
                    "campaign_id": campaign_id,
                    "binom_id": data["binom_id"],
                    "name": data["name"],
                    "group": data["group"],
                    "total_clicks": data["total_clicks"],
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "total_leads": data["total_leads"],
                    "avg_daily_spend": round(avg_daily_spend, 2),
                    "roi": round(roi, 1),
                    "cr": round(cr, 2)
                }

                small_campaigns.append(campaign_info)
                all_rois.append(roi)
                all_crs.append(cr)
                all_costs.append(data["total_cost"])

            if not small_campaigns:
                return {
                    "clusters": [],
                    "summary": {
                        "total_clusters": 0,
                        "total_campaigns": 0,
                        "total_small_campaigns": 0,
                        "avg_cluster_size": 0
                    },
                    "period": {
                        "days": days,
                        "date_from": date_from.isoformat(),
                        "date_to": datetime.now().date().isoformat()
                    },
                    "params": {
                        "max_daily_spend": max_daily_spend,
                        "min_campaigns_per_cluster": min_campaigns_per_cluster,
                        "similarity_threshold": similarity_threshold,
                        "min_total_clicks": min_total_clicks
                    }
                }

            # Нормализация метрик для кластеризации
            min_roi = min(all_rois)
            max_roi = max(all_rois)
            min_cr = min(all_crs)
            max_cr = max(all_crs)
            min_cost = min(all_costs)
            max_cost = max(all_costs)

            # Создание векторов признаков для каждой кампании
            for campaign in small_campaigns:
                norm_roi = self._normalize_value(campaign["roi"], min_roi, max_roi)
                norm_cr = self._normalize_value(campaign["cr"], min_cr, max_cr)
                norm_cost = self._normalize_value(campaign["total_cost"], min_cost, max_cost)

                campaign["feature_vector"] = [norm_roi, norm_cr, norm_cost]

            # Простая кластеризация методом ближайшего соседа
            clusters = []
            small_clusters = []  # Для кластеров меньше минимального размера
            used_campaigns = set()

            for i, campaign in enumerate(small_campaigns):
                if i in used_campaigns:
                    continue

                cluster = {
                    "cluster_id": len(clusters) + len(small_clusters) + 1,
                    "campaigns": [campaign],
                    "campaign_ids": [campaign["campaign_id"]],
                    "total_cost": campaign["total_cost"],
                    "total_revenue": campaign["total_revenue"],
                    "total_clicks": campaign["total_clicks"],
                    "avg_roi": campaign["roi"],
                    "avg_cr": campaign["cr"]
                }
                used_campaigns.add(i)

                # Поиск похожих кампаний
                for j, other_campaign in enumerate(small_campaigns):
                    if j in used_campaigns:
                        continue

                    similarity = self._cosine_similarity(
                        campaign["feature_vector"],
                        other_campaign["feature_vector"]
                    )

                    if similarity >= similarity_threshold:
                        cluster["campaigns"].append(other_campaign)
                        cluster["campaign_ids"].append(other_campaign["campaign_id"])
                        cluster["total_cost"] += other_campaign["total_cost"]
                        cluster["total_revenue"] += other_campaign["total_revenue"]
                        cluster["total_clicks"] += other_campaign["total_clicks"]
                        used_campaigns.add(j)

                # Пересчет средних метрик для всех кластеров
                cluster["avg_roi"] = round(
                    sum(c["roi"] for c in cluster["campaigns"]) / len(cluster["campaigns"]), 1
                )
                cluster["avg_cr"] = round(
                    sum(c["cr"] for c in cluster["campaigns"]) / len(cluster["campaigns"]), 2
                )
                cluster["total_cost"] = round(cluster["total_cost"], 2)
                cluster["total_revenue"] = round(cluster["total_revenue"], 2)
                cluster["campaign_count"] = len(cluster["campaigns"])

                # Удаляем feature_vector из кампаний для чистоты вывода
                for c in cluster["campaigns"]:
                    if "feature_vector" in c:
                        del c["feature_vector"]

                # Добавляем в соответствующий список
                if len(cluster["campaigns"]) >= min_campaigns_per_cluster:
                    clusters.append(cluster)
                else:
                    # Сохраняем малые кластеры отдельно (не теряем данные)
                    small_clusters.append(cluster)

            # Сортировка кластеров по ROI (убывание)
            clusters.sort(key=lambda x: x["avg_roi"], reverse=True)
            small_clusters.sort(key=lambda x: x["avg_roi"], reverse=True)

            # Подсчет всех обработанных кампаний
            total_campaigns_in_clusters = sum(c["campaign_count"] for c in clusters)
            total_campaigns_in_small_clusters = sum(c["campaign_count"] for c in small_clusters)

            return {
                "clusters": clusters,
                "small_clusters": small_clusters,  # Кластеры размером < min_campaigns_per_cluster
                "summary": {
                    "total_clusters": len(clusters),
                    "total_campaigns": total_campaigns_in_clusters,
                    "total_small_campaigns": len(small_campaigns),
                    "small_clusters_count": len(small_clusters),
                    "campaigns_in_small_clusters": total_campaigns_in_small_clusters,
                    "avg_cluster_size": round(
                        sum(c["campaign_count"] for c in clusters) / len(clusters), 1
                    ) if clusters else 0
                },
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "max_daily_spend": max_daily_spend,
                    "min_campaigns_per_cluster": min_campaigns_per_cluster,
                    "similarity_threshold": similarity_threshold,
                    "min_total_clicks": min_total_clicks
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        clusters = raw_data.get("clusters", [])
        summary = raw_data.get("summary", {})

        if not clusters:
            return []

        charts = []

        # График распределения кластеров по размеру
        cluster_sizes = [c["campaign_count"] for c in clusters]
        charts.append({
            "id": "consolidator_cluster_sizes",
            "type": "bar",
            "data": {
                "labels": [f"Кластер {c['cluster_id']}" for c in clusters],
                "datasets": [{
                    "label": "Количество кампаний",
                    "data": cluster_sizes,
                    "backgroundColor": "rgba(54, 162, 235, 0.6)",
                    "borderColor": "rgba(54, 162, 235, 1)",
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Распределение кампаний по кластерам"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "Кол-во кампаний"
                        }
                    }
                }
            }
        })

        # График ROI кластеров
        charts.append({
            "id": "consolidator_cluster_roi",
            "type": "bar",
            "data": {
                "labels": [f"Кластер {c['cluster_id']}" for c in clusters],
                "datasets": [{
                    "label": "Средний ROI (%)",
                    "data": [c["avg_roi"] for c in clusters],
                    "backgroundColor": [
                        "rgba(75, 192, 192, 0.6)" if roi > 0 else "rgba(255, 99, 132, 0.6)"
                        for roi in [c["avg_roi"] for c in clusters]
                    ],
                    "borderColor": [
                        "rgba(75, 192, 192, 1)" if roi > 0 else "rgba(255, 99, 132, 1)"
                        for roi in [c["avg_roi"] for c in clusters]
                    ],
                    "borderWidth": 1
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Средний ROI по кластерам"
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": "ROI (%)"
                        }
                    }
                }
            }
        })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация алертов для кластеров малобюджетных кампаний.
        """
        clusters = raw_data.get("clusters", [])
        alerts = []

        # Находим кластеры с высоким ROI для возможного масштабирования
        high_roi_clusters = [c for c in clusters if c["avg_roi"] > 50]
        if high_roi_clusters:
            message = f"Обнаружено {len(high_roi_clusters)} кластеров малобюджетных кампаний с высоким ROI (>50%)\n\n"
            message += "Топ-3 кластера для масштабирования:\n"

            for i, cluster in enumerate(high_roi_clusters[:3], 1):
                message += f"{i}. Кластер {cluster['cluster_id']}: "
                message += f"{cluster['campaign_count']} кампаний, "
                message += f"средний ROI {cluster['avg_roi']:.1f}%\n"

            alerts.append({
                "type": "consolidator_high_roi",
                "severity": "high",
                "message": message,
                "recommended_action": "Рассмотрите возможность масштабирования этих кластеров",
                "clusters_count": len(high_roi_clusters),
                "avg_roi": round(sum(c["avg_roi"] for c in high_roi_clusters) / len(high_roi_clusters), 1)
            })

        return alerts
