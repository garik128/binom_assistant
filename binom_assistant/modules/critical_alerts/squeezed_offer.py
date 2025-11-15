"""
Модуль детекции отжатых офферов (падение конверсии или апрувов)
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from contextlib import contextmanager

from storage.database.base import get_session
from storage.database.models import Offer, OfferStatsDaily
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


class SqueezedOfferDetector(BaseModule):
    """
    Детектор отжатых офферов.

    Находит офферы с падением эффективности - либо снижается CR
    (меньше лидов при том же трафике), либо падает процент апрувленных
    лидов от общего количества (учитывая rejected + hold).

    Критерии:
    - Падение CR > 40% (текущие 7 дней vs предыдущие 7 дней) ИЛИ
    - Approve rate от общих лидов падает > 40% от нормы
    - Объем трафика стабилен (±20%)
    - Минимум 20 лидов за последние 7 дней
    - Учитываются все статусы лидов: approved, rejected, hold
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="squeezed_offer",
            name="Отжатый оффер",
            category="critical_alerts",
            description="Обнаруживает офферы с падением CR или процента апрувов",
            detailed_description=(
                "Модуль выявляет офферы с падением эффективности: снижение CR "
                "(меньше лидов при том же трафике) или падение процента апрувленных "
                "лидов. Помогает быстро обнаружить проблемы с оффером, лендингом "
                "или требованиями партнёрки. Анализирует только полные дни, исключая сегодняшний (апрувы приходят с задержкой)."
            ),
            version="1.1.0",
            author="Binom Assistant",
            priority="critical",
            tags=["offers", "cr", "approve_rate", "quality", "conversion"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="0 9 * * *",  # ежедневно в 9:00
            alerts_enabled=True,  # Критический модуль - алерты включены по умолчанию
            timeout_seconds=45,
            cache_ttl_seconds=3600,
            params={
                "days": 7,  # период анализа (текущие 7 дней включительно)
                "cr_drop_threshold": 40,  # падение CR более 40%
                "approve_drop_threshold": 40,  # падение approve rate более 40%
                "min_leads": 20,  # минимум 20 лидов за период
                "traffic_stability": 20,  # стабильность трафика ±20%
                "severity_critical": 60,  # падение метрик для critical severity
                "severity_high": 50  # падение метрик для high severity
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
                "description": "Количество дней для анализа текущего и предыдущего периода (включая сегодня)",
                "type": "number",
                "min": 3,
                "max": 365,
                "step": 1
            },
            "cr_drop_threshold": {
                "label": "Порог падения CR (%)",
                "description": "Минимальное падение конверсии для детекции проблемы",
                "type": "number",
                "min": 10,
                "max": 90,
                "step": 5
            },
            "approve_drop_threshold": {
                "label": "Порог падения апрувов (%)",
                "description": "Минимальное падение процента апрувов для детекции проблемы",
                "type": "number",
                "min": 10,
                "max": 90,
                "step": 5
            },
            "min_leads": {
                "label": "Минимум лидов",
                "description": "Минимальное количество лидов за текущий период для анализа",
                "type": "number",
                "min": 5,
                "max": 1000,
                "step": 5
            },
            "traffic_stability": {
                "label": "Стабильность трафика (±%)",
                "description": "Допустимое отклонение объема трафика между периодами",
                "type": "number",
                "min": 10,
                "max": 50,
                "step": 5
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "drop_percent",
            "metric_label": "Падение метрик",
            "metric_unit": "%",
            "description": "Пороги критичности на основе падения CR или процента апрувов (берется максимальное падение)",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичное падение",
                    "description": "Падение метрик (CR или approve rate) для критичного уровня",
                    "type": "number",
                    "min": 40,
                    "max": 100,
                    "step": 5,
                    "default": 60
                },
                "severity_high": {
                    "label": "Высокое падение",
                    "description": "Падение метрик (CR или approve rate) для высокого уровня",
                    "type": "number",
                    "min": 30,
                    "max": 90,
                    "step": 5,
                    "default": 50
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "Падение >= critical%"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical% > Падение >= high%"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "Падение < high%"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ отжатых офферов через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные об отжатых офферах
        """
        # Получение параметров
        days = config.params.get("days", 7)
        cr_drop_threshold = config.params.get("cr_drop_threshold", 40)
        approve_drop_threshold = config.params.get("approve_drop_threshold", 40)
        min_leads = config.params.get("min_leads", 20)
        traffic_stability = config.params.get("traffic_stability", 20)

        # Получение настраиваемых порогов severity
        severity_critical_threshold = config.params.get("severity_critical", 60)
        severity_high_threshold = config.params.get("severity_high", 50)

        # Расчет дат (исключаем сегодняшний день - апрувы приходят с задержкой)
        yesterday = datetime.now().date() - timedelta(days=1)
        current_period_start = yesterday - timedelta(days=days - 1)
        previous_period_start = current_period_start - timedelta(days=days)
        previous_period_end = current_period_start - timedelta(days=1)

        # Работа с БД
        with get_db_session() as session:
            # Получаем статистику по офферам для обоих периодов
            query = session.query(
                Offer.id,
                Offer.name,
                Offer.network_id,
                Offer.geo,
                OfferStatsDaily.date,
                OfferStatsDaily.clicks,
                OfferStatsDaily.leads,
                OfferStatsDaily.a_leads,
                OfferStatsDaily.h_leads,
                OfferStatsDaily.r_leads,
                OfferStatsDaily.cost,
                OfferStatsDaily.revenue
            ).join(
                OfferStatsDaily,
                Offer.id == OfferStatsDaily.offer_id
            ).filter(
                OfferStatsDaily.date >= previous_period_start,
                OfferStatsDaily.date <= yesterday,
                OfferStatsDaily.cost > 0
            ).order_by(
                Offer.id,
                OfferStatsDaily.date
            )

            stats_by_date = query.all()

            # Группируем данные по офферам и периодам
            offers_data = {}
            for row in stats_by_date:
                offer_id = row.id
                if offer_id not in offers_data:
                    offers_data[offer_id] = {
                        'offer_name': row.name,
                        'network_id': row.network_id,
                        'geo': row.geo,
                        'current_period': [],
                        'previous_period': []
                    }

                # Определяем к какому периоду относится запись
                if current_period_start <= row.date <= yesterday:
                    period = 'current_period'
                elif previous_period_start <= row.date <= previous_period_end:
                    period = 'previous_period'
                else:
                    continue

                offers_data[offer_id][period].append({
                    'date': row.date,
                    'clicks': int(row.clicks) if row.clicks else 0,
                    'leads': int(row.leads) if row.leads else 0,
                    'a_leads': int(row.a_leads) if row.a_leads else 0,
                    'h_leads': int(row.h_leads) if row.h_leads else 0,
                    'r_leads': int(row.r_leads) if row.r_leads else 0,
                    'cost': float(row.cost) if row.cost else 0.0,
                    'revenue': float(row.revenue) if row.revenue else 0.0
                })

            # Анализируем отжатые офферы
            squeezed_offers = []

            for offer_id, periods_data in offers_data.items():
                current_data = periods_data['current_period']
                previous_data = periods_data['previous_period']

                # Пропускаем если недостаточно данных
                if not current_data or not previous_data:
                    continue

                # Агрегируем статистику по периодам
                # Текущий период
                current_clicks = sum(d['clicks'] for d in current_data)
                current_leads = sum(d['leads'] for d in current_data)
                current_a_leads = sum(d['a_leads'] for d in current_data)
                current_h_leads = sum(d['h_leads'] for d in current_data)
                current_r_leads = sum(d['r_leads'] for d in current_data)
                current_cost = sum(d['cost'] for d in current_data)
                current_revenue = sum(d['revenue'] for d in current_data)

                # Предыдущий период
                previous_clicks = sum(d['clicks'] for d in previous_data)
                previous_leads = sum(d['leads'] for d in previous_data)
                previous_a_leads = sum(d['a_leads'] for d in previous_data)
                previous_h_leads = sum(d['h_leads'] for d in previous_data)
                previous_r_leads = sum(d['r_leads'] for d in previous_data)
                previous_cost = sum(d['cost'] for d in previous_data)
                previous_revenue = sum(d['revenue'] for d in previous_data)

                # Фильтрация: минимум лидов
                if current_leads < min_leads:
                    continue

                # Проверка стабильности трафика (±20% по умолчанию)
                if previous_clicks > 0:
                    traffic_change = abs(current_clicks - previous_clicks) / previous_clicks * 100
                    if traffic_change > traffic_stability:
                        continue
                else:
                    continue

                # Вычисляем метрики
                # CR (Conversion Rate)
                current_cr = (current_leads / current_clicks * 100) if current_clicks > 0 else 0
                previous_cr = (previous_leads / previous_clicks * 100) if previous_clicks > 0 else 0

                # Approve Rate (процент апрувов от ВСЕХ лидов включая hold и rejected)
                current_total_leads = current_a_leads + current_h_leads + current_r_leads
                previous_total_leads = previous_a_leads + previous_h_leads + previous_r_leads

                current_approve_rate = (current_a_leads / current_total_leads * 100) if current_total_leads > 0 else 0
                previous_approve_rate = (previous_a_leads / previous_total_leads * 100) if previous_total_leads > 0 else 0

                # ROI
                current_roi = ((current_revenue - current_cost) / current_cost * 100) if current_cost > 0 else 0
                previous_roi = ((previous_revenue - previous_cost) / previous_cost * 100) if previous_cost > 0 else 0

                # Вычисляем изменения
                cr_change = 0
                approve_rate_change = 0
                is_squeezed = False
                problem_type = []

                # Проверка падения CR
                if previous_cr > 0:
                    cr_change = ((current_cr - previous_cr) / previous_cr) * 100
                    if cr_change < -cr_drop_threshold:
                        is_squeezed = True
                        problem_type.append("CR падение")

                # Проверка падения Approve Rate
                if previous_approve_rate > 0:
                    approve_rate_change = ((current_approve_rate - previous_approve_rate) / previous_approve_rate) * 100
                    if approve_rate_change < -approve_drop_threshold:
                        is_squeezed = True
                        problem_type.append("Апрувы падение")

                # Если не обнаружено отжатия, пропускаем
                if not is_squeezed:
                    continue

                # Определение критичности на основе максимального падения
                max_drop = max(abs(cr_change), abs(approve_rate_change))
                if max_drop >= severity_critical_threshold:
                    severity = "critical"
                elif max_drop >= severity_high_threshold:
                    severity = "high"
                else:
                    severity = "medium"

                # Формируем данные
                offer_name = periods_data.get('offer_name', f"Offer {offer_id}")
                network_id = periods_data.get('network_id')
                geo = periods_data.get('geo')

                squeezed_offers.append({
                    "offer_id": offer_id,
                    "offer_name": offer_name,
                    "network_id": network_id,
                    "geo": geo,

                    # Текущий период
                    "current_cr": round(current_cr, 2),
                    "current_approve_rate": round(current_approve_rate, 2),
                    "current_clicks": current_clicks,
                    "current_leads": current_leads,
                    "current_a_leads": current_a_leads,
                    "current_roi": round(current_roi, 2),

                    # Предыдущий период
                    "previous_cr": round(previous_cr, 2),
                    "previous_approve_rate": round(previous_approve_rate, 2),
                    "previous_clicks": previous_clicks,
                    "previous_leads": previous_leads,
                    "previous_a_leads": previous_a_leads,
                    "previous_roi": round(previous_roi, 2),

                    # Изменения
                    "cr_change": round(cr_change, 2),
                    "approve_rate_change": round(approve_rate_change, 2),
                    "roi_change": round(current_roi - previous_roi, 2),

                    # Обязательные поля
                    "total_cost": round(current_cost + previous_cost, 2),
                    "total_revenue": round(current_revenue + previous_revenue, 2),
                    "avg_roi": round((current_roi + previous_roi) / 2, 2),

                    # Дополнительная информация
                    "problem_type": ", ".join(problem_type),
                    "severity": severity,
                    "total_leads": current_leads + previous_leads
                })

            # Сортировка: сначала по критичности, затем по величине падения
            squeezed_offers.sort(
                key=lambda x: (
                    {"critical": 0, "high": 1, "medium": 2}[x['severity']],
                    min(x['cr_change'], x['approve_rate_change'])
                )
            )

            return {
                "offers": squeezed_offers,
                "summary": {
                    "total_found": len(squeezed_offers),
                    "critical_count": sum(1 for o in squeezed_offers if o['severity'] == 'critical'),
                    "high_count": sum(1 for o in squeezed_offers if o['severity'] == 'high'),
                    "medium_count": sum(1 for o in squeezed_offers if o['severity'] == 'medium'),
                    "avg_cr_drop": round(
                        sum(o['cr_change'] for o in squeezed_offers) / len(squeezed_offers), 2
                    ) if squeezed_offers else 0,
                    "avg_approve_rate_drop": round(
                        sum(o['approve_rate_change'] for o in squeezed_offers) / len(squeezed_offers), 2
                    ) if squeezed_offers else 0
                },
                "period": {
                    "current_start": current_period_start.isoformat(),
                    "current_end": yesterday.isoformat(),
                    "previous_start": previous_period_start.isoformat(),
                    "previous_end": previous_period_end.isoformat(),
                    "days": days
                },
                "thresholds": {
                    "cr_drop_threshold": cr_drop_threshold,
                    "approve_drop_threshold": approve_drop_threshold,
                    "min_leads": min_leads,
                    "traffic_stability": traffic_stability,
                    "severity_critical": severity_critical_threshold,
                    "severity_high": severity_high_threshold
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
        offers = raw_data["offers"][:10]  # Топ-10

        if not offers:
            return []

        charts = []

        # График 1: Падение CR
        cr_drops = [c for c in offers if "CR падение" in c['problem_type']]
        if cr_drops:
            charts.append({
                "id": "cr_drop_chart",
                "type": "bar",
                "data": {
                    "labels": [f"[{c['offer_id']}] {c['offer_name'][:20]}" for c in cr_drops[:10]],
                    "datasets": [{
                        "label": "Падение CR (%)",
                        "data": [c["cr_change"] for c in cr_drops[:10]],
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
                            "text": "Топ-10 офферов с падением конверсии"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": False
                        }
                    }
                }
            })

        # График 2: Падение Approve Rate
        approve_drops = [c for c in offers if "Апрувы падение" in c['problem_type']]
        if approve_drops:
            charts.append({
                "id": "approve_drop_chart",
                "type": "bar",
                "data": {
                    "labels": [f"[{c['offer_id']}] {c['offer_name'][:20]}" for c in approve_drops[:10]],
                    "datasets": [{
                        "label": "Падение процента апрувов (%)",
                        "data": [c["approve_rate_change"] for c in approve_drops[:10]],
                        "backgroundColor": "rgba(251, 146, 60, 0.5)",
                        "borderColor": "rgba(251, 146, 60, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Топ-10 офферов с падением апрувов"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": False
                        }
                    }
                }
            })

        # График 3: Распределение по типам проблем
        summary = raw_data["summary"]
        if summary["total_found"] > 0:
            charts.append({
                "id": "severity_distribution",
                "type": "doughnut",
                "data": {
                    "labels": ["Критические", "Высокая важность", "Средняя важность"],
                    "datasets": [{
                        "data": [
                            summary["critical_count"],
                            summary["high_count"],
                            summary["medium_count"]
                        ],
                        "backgroundColor": [
                            "rgba(239, 68, 68, 0.8)",
                            "rgba(251, 146, 60, 0.8)",
                            "rgba(234, 179, 8, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение по критичности"
                        }
                    }
                }
            })

        return charts

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов для отжатых офферов.
        """
        alerts = []
        summary = raw_data["summary"]
        offers = raw_data["offers"]
        thresholds = raw_data.get("thresholds", {})

        # Если есть отжатые офферы, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]
            avg_cr_drop = summary["avg_cr_drop"]
            avg_approve_drop = summary["avg_approve_rate_drop"]

            # Получаем пороги для сообщения
            severity_critical_threshold = thresholds.get("severity_critical", 60)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: Обнаружено {total_found} отжатых офферов!"
                if critical_count > 1:
                    message += f" (из них {critical_count} критических с падением >{severity_critical_threshold}%)"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: Обнаружено {total_found} офферов с падением эффективности"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} офферов показывают падение метрик"

            message += f"\nСреднее падение CR: {avg_cr_drop:.1f}%"
            message += f"\nСреднее падение апрувов: {avg_approve_drop:.1f}%"

            # Добавляем краткую информацию о топ-3
            top_3 = offers[:3]
            if top_3:
                message += "\n\nТоп-3 проблемных:"
                for i, campaign in enumerate(top_3, 1):
                    problem_desc = []
                    if campaign['cr_change'] < -40:
                        problem_desc.append(f"CR {campaign['cr_change']:.1f}%")
                    if campaign['approve_rate_change'] < -40:
                        problem_desc.append(f"Апрувы {campaign['approve_rate_change']:.1f}%")

                    message += f"\n{i}. [{campaign['offer_id']}] {campaign['offer_name']}: {', '.join(problem_desc)}"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Срочно проверьте лендинги и требования партнёрок. Возможно изменились условия офферов"
            else:
                recommended_action = "Проанализируйте причины падения конверсии и апрувов"

            alerts.append({
                "type": "squeezed_offers_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "offers_count": total_found,
                "critical_count": critical_count
            })

        return alerts
