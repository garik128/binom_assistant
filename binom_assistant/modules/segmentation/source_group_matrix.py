"""
Модуль матрицы источник-группа (Source-Group Matrix)
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


class SourceGroupMatrix(BaseModule):
    """
    Матрица эффективности источник-группа.

    Создает двумерную матрицу показывающую эффективность каждой пары источник-группа кампаний.
    Основа для стратегического планирования.

    Логика построения матрицы:
    - Агрегация данных по источникам (ts_name) и группам кампаний (group_name)
    - Расчет среднего ROI для каждой ячейки
    - Цветовое кодирование по эффективности
    - Выделение лучших и худших комбинаций
    - Минимальный расход > min_cell_spend для включения в матрицу
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="source_group_matrix",
            name="Матрица источник-группа",
            category="segmentation",
            description="Построение матрицы эффективности источник-группа",
            detailed_description="Создает двумерную матрицу показывающую эффективность каждой пары источник-группа кампаний. Помогает определить лучшие и худшие комбинации для стратегического планирования.",
            version="1.0.0",
            author="Binom Assistant",
            priority="medium",
            tags=["segmentation", "matrix", "source", "group", "roi"]
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
                "min_cell_spend": 10.0,  # минимальный расход для ячейки матрицы ($)
                "min_campaigns": 1  # минимум кампаний для ячейки
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество дней для анализа",
                "type": "number",
                "min": 3,
                "max": 365,
                "default": 7
            },
            "min_cell_spend": {
                "label": "Минимальный расход для ячейки ($)",
                "description": "Минимальный общий расход для включения ячейки в матрицу",
                "type": "number",
                "min": 5,
                "max": 10000,
                "default": 10.0
            },
            "min_campaigns": {
                "label": "Минимум кампаний",
                "description": "Минимальное количество кампаний для ячейки матрицы",
                "type": "number",
                "min": 1,
                "max": 10,
                "default": 1
            }
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ и построение матрицы источник-оффер.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные матрицы источник-оффер
        """
        # Получение параметров
        days = config.params.get("days", 7)
        min_cell_spend = config.params.get("min_cell_spend", 10.0)
        min_campaigns = config.params.get("min_campaigns", 1)

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
                Campaign.ts_name,
                CampaignStatsDaily.date,
                CampaignStatsDaily.clicks,
                CampaignStatsDaily.cost,
                CampaignStatsDaily.revenue,
                CampaignStatsDaily.leads
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

            # Группировка по источнику и офферу
            matrix_data = defaultdict(lambda: {
                "campaigns": set(),
                "total_clicks": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0,
                "campaign_details": []
            })

            campaign_info = defaultdict(lambda: {
                "binom_id": None,
                "name": None,
                "source": None,
                "group": None,
                "total_clicks": 0,
                "total_cost": 0,
                "total_revenue": 0,
                "total_leads": 0
            })

            for row in results:
                campaign_id = row.internal_id
                source = row.ts_name or "Неизвестный источник"
                group = row.group_name or "Без группы"

                # Ключ матрицы
                matrix_key = (source, group)

                # Агрегация для матрицы
                matrix_data[matrix_key]["campaigns"].add(campaign_id)
                matrix_data[matrix_key]["total_clicks"] += row.clicks or 0
                matrix_data[matrix_key]["total_cost"] += float(row.cost) if row.cost else 0
                matrix_data[matrix_key]["total_revenue"] += float(row.revenue) if row.revenue else 0
                matrix_data[matrix_key]["total_leads"] += row.leads or 0

                # Информация о кампании
                campaign_info[campaign_id]["binom_id"] = row.binom_id
                campaign_info[campaign_id]["name"] = row.current_name
                campaign_info[campaign_id]["source"] = source
                campaign_info[campaign_id]["group"] = group
                campaign_info[campaign_id]["total_clicks"] += row.clicks or 0
                campaign_info[campaign_id]["total_cost"] += float(row.cost) if row.cost else 0
                campaign_info[campaign_id]["total_revenue"] += float(row.revenue) if row.revenue else 0
                campaign_info[campaign_id]["total_leads"] += row.leads or 0

            # Подготовка ячеек матрицы
            matrix_cells = []
            all_sources = set()
            all_groups = set()

            for (source, group), data in matrix_data.items():
                # Фильтры
                if data["total_cost"] < min_cell_spend:
                    continue
                if len(data["campaigns"]) < min_campaigns:
                    continue

                all_sources.add(source)
                all_groups.add(group)

                # Расчет метрик
                roi = ((data["total_revenue"] - data["total_cost"]) / data["total_cost"] * 100) if data["total_cost"] > 0 else -100
                cr = (data["total_leads"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0
                profit = data["total_revenue"] - data["total_cost"]

                # Подготовка деталей кампаний
                campaign_details = []
                for camp_id in data["campaigns"]:
                    camp = campaign_info[camp_id]
                    camp_roi = ((camp["total_revenue"] - camp["total_cost"]) / camp["total_cost"] * 100) if camp["total_cost"] > 0 else -100

                    campaign_details.append({
                        "campaign_id": camp_id,
                        "binom_id": camp["binom_id"],
                        "name": camp["name"],
                        "cost": round(camp["total_cost"], 2),
                        "revenue": round(camp["total_revenue"], 2),
                        "roi": round(camp_roi, 1)
                    })

                campaign_details.sort(key=lambda x: x["roi"], reverse=True)

                cell = {
                    "source": source,
                    "group": group,
                    "campaigns_count": len(data["campaigns"]),
                    "total_clicks": data["total_clicks"],
                    "total_cost": round(data["total_cost"], 2),
                    "total_revenue": round(data["total_revenue"], 2),
                    "total_leads": data["total_leads"],
                    "profit": round(profit, 2),
                    "roi": round(roi, 1),
                    "cr": round(cr, 2),
                    "campaign_details": campaign_details
                }

                matrix_cells.append(cell)

            if not matrix_cells:
                return {
                    "matrix_cells": [],
                    "sources": [],
                    "groups": [],
                    "summary": {
                        "total_cells": 0,
                        "total_campaigns": 0,
                        "profitable_cells": 0,
                        "unprofitable_cells": 0
                    },
                    "best_combinations": [],
                    "worst_combinations": [],
                    "period": {
                        "days": days,
                        "date_from": date_from.isoformat(),
                        "date_to": datetime.now().date().isoformat()
                    },
                    "params": {
                        "min_cell_spend": min_cell_spend,
                        "min_campaigns": min_campaigns
                    }
                }

            # Сортировка ячеек по ROI (для выделения лучших/худших)
            sorted_cells = sorted(matrix_cells, key=lambda x: x["roi"], reverse=True)

            # Топ-5 лучших и худших комбинаций
            best_combinations = sorted_cells[:5]
            worst_combinations = sorted_cells[-5:][::-1]  # Разворачиваем чтобы худшие были первыми

            # Подсчет прибыльных/убыточных ячеек
            profitable_cells = sum(1 for cell in matrix_cells if cell["profit"] > 0)
            unprofitable_cells = sum(1 for cell in matrix_cells if cell["profit"] < 0)

            return {
                "matrix_cells": matrix_cells,
                "sources": sorted(list(all_sources)),
                "groups": sorted(list(all_groups)),
                "summary": {
                    "total_cells": len(matrix_cells),
                    "total_campaigns": sum(len(data["campaigns"]) for data in matrix_data.values()),
                    "profitable_cells": profitable_cells,
                    "unprofitable_cells": unprofitable_cells
                },
                "best_combinations": best_combinations,
                "worst_combinations": worst_combinations,
                "period": {
                    "days": days,
                    "date_from": date_from.isoformat(),
                    "date_to": datetime.now().date().isoformat()
                },
                "params": {
                    "min_cell_spend": min_cell_spend,
                    "min_campaigns": min_campaigns
                }
            }

    def generate_recommendations(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций - ОТКЛЮЧЕНО.
        """
        return []

    def prepare_chart_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготовка данных для Chart.js"""
        best_combinations = raw_data.get("best_combinations", [])
        worst_combinations = raw_data.get("worst_combinations", [])

        if not best_combinations and not worst_combinations:
            return []

        charts = []

        # График лучших комбинаций
        if best_combinations:
            charts.append({
                "id": "matrix_best_combinations",
                "type": "bar",
                "data": {
                    "labels": [f"{c['source']} → {c['group']}" for c in best_combinations],
                    "datasets": [{
                        "label": "ROI (%)",
                        "data": [c["roi"] for c in best_combinations],
                        "backgroundColor": "rgba(75, 192, 192, 0.6)",
                        "borderColor": "rgba(75, 192, 192, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-5 лучших комбинаций источник-оффер"
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

        # График худших комбинаций
        if worst_combinations:
            charts.append({
                "id": "matrix_worst_combinations",
                "type": "bar",
                "data": {
                    "labels": [f"{c['source']} → {c['group']}" for c in worst_combinations],
                    "datasets": [{
                        "label": "ROI (%)",
                        "data": [c["roi"] for c in worst_combinations],
                        "backgroundColor": "rgba(255, 99, 132, 0.6)",
                        "borderColor": "rgba(255, 99, 132, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-5 худших комбинаций источник-оффер"
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
        Генерация алертов для матрицы источник-оффер.
        """
        worst_combinations = raw_data.get("worst_combinations", [])
        alerts = []

        # Находим худшие комбинации с убытком
        losing_combinations = [c for c in worst_combinations if c["profit"] < 0]
        if losing_combinations:
            total_loss = sum(abs(c["profit"]) for c in losing_combinations)

            message = f"Обнаружено {len(losing_combinations)} убыточных комбинаций источник-оффер\n\n"
            message += f"Общий убыток: ${total_loss:.2f}\n\n"
            message += "Топ-3 худших комбинации:\n"

            for i, combo in enumerate(losing_combinations[:3], 1):
                message += f"{i}. {combo['source']} → {combo['group']}: "
                message += f"ROI {combo['roi']:.1f}%, убыток ${abs(combo['profit']):.2f}, "
                message += f"кампаний: {combo['campaigns_count']}\n"

            alerts.append({
                "type": "matrix_losing_combinations",
                "severity": "high",
                "message": message,
                "recommended_action": "Рассмотрите возможность остановки или оптимизации этих комбинаций",
                "combinations_count": len(losing_combinations),
                "total_loss": round(total_loss, 2)
            })

        return alerts
