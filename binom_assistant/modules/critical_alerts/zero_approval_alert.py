"""
Модуль поиска кампаний с нулевым процентом апрувов
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


class ZeroApprovalAlert(BaseModule):
    """
    Детектор кампаний с нулевыми апрувами при наличии лидов.

    Находит кампании, которые генерируют лиды, но не получают апрувов.
    Помогает выявить проблемы с качеством трафика или оффером.

    Критерии:
    - Количество лидов > 10 (настраивается)
    - Количество апрувленных лидов = 0
    - Минимальный расход > $10 (настраивается)
    - Период анализа: последние 7 дней (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="zero_approval_alert",
            name="Нет апрувов",
            category="critical_alerts",
            description="Находит кампании с нулевыми апрувами при наличии лидов",
            detailed_description="Модуль обнаруживает кампании, которые генерируют лиды, но не получают апрувов. Это может указывать на проблемы с качеством трафика, настройками оффера или технические проблемы с постбэком.",
            version="1.0.3",  # русское название
            author="Binom Assistant",
            priority="critical",
            tags=["approval", "leads", "quality", "critical"]
        )

    def get_default_config(self) -> ModuleConfig:
        """Возвращает конфигурацию по умолчанию"""
        return ModuleConfig(
            enabled=True,
            schedule="",  # Критический модуль - автозапуск выключен по умолчанию
            alerts_enabled=False,  # Алерты выключены по умолчанию
            timeout_seconds=30,
            cache_ttl_seconds=3600,
            params={
                "min_leads": 10,  # минимум 10 лидов
                "min_spend": 10,  # минимум $10 трат
                "days": 7,  # за последние 7 дней
                "severity_critical": 5,  # кратность расхода для critical severity
                "severity_high": 2  # кратность расхода для high severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "min_leads": {
                "label": "Минимум лидов",
                "description": "Минимальное количество лидов для включения в анализ",
                "type": "number",
                "min": 5,
                "max": 1000,
                "step": 5
            },
            "min_spend": {
                "label": "Минимальный расход ($)",
                "description": "Минимальный расход для включения в анализ",
                "type": "number",
                "min": 1,
                "max": 10000,
                "step": 1
            },
            "days": {
                "label": "Период анализа (дней)",
                "description": "Количество последних дней для анализа",
                "type": "number",
                "min": 1,
                "max": 365,
                "step": 1
            }
        }

    def get_severity_metadata(self) -> Dict[str, Any]:
        """Возвращает метаданные для настройки порогов severity"""
        return {
            "enabled": True,
            "metric": "spend_multiplier",
            "metric_label": "Кратность расхода",
            "metric_unit": "x",
            "description": "Пороги критичности на основе превышения минимального расхода",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичная кратность",
                    "description": "Превышение минимального расхода для критичного уровня (кратность)",
                    "type": "number",
                    "min": 2,
                    "max": 10,
                    "step": 0.5,
                    "default": 5
                },
                "severity_high": {
                    "label": "Высокая кратность",
                    "description": "Превышение минимального расхода для высокого уровня (кратность)",
                    "type": "number",
                    "min": 1,
                    "max": 10,
                    "step": 0.5,
                    "default": 2
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "Кратность >= critical"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical > Кратность >= high"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "Кратность < high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ кампаний с нулевыми апрувами через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные о кампаниях с нулевыми апрувами
        """
        # Получение параметров
        min_leads = config.params.get("min_leads", 10)
        min_spend = config.params.get("min_spend", 10)
        days = config.params.get("days", 7)

        # Получение настраиваемых порогов severity
        severity_critical_threshold = config.params.get("severity_critical", 5)
        severity_high_threshold = config.params.get("severity_high", 2)

        # Анализируем только полные дни (исключаем текущий неполный день)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Запрос: агрегированная статистика по кампаниям за период
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                func.sum(CampaignStatsDaily.cost).label('total_cost'),
                func.sum(CampaignStatsDaily.revenue).label('total_revenue'),
                func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
                func.sum(CampaignStatsDaily.leads).label('total_leads'),
                func.sum(CampaignStatsDaily.a_leads).label('total_a_leads'),
                func.sum(CampaignStatsDaily.h_leads).label('total_h_leads'),
                func.sum(CampaignStatsDaily.r_leads).label('total_r_leads')
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost > 0,  # только активные
                Campaign.is_cpl_mode == False  # только CPA кампании (CPL всегда имеют a_leads=0)
            ).group_by(
                Campaign.internal_id
            ).having(
                func.sum(CampaignStatsDaily.cost) >= min_spend,
                func.sum(CampaignStatsDaily.leads) > min_leads,
                func.sum(CampaignStatsDaily.a_leads) == 0
            )

            results = query.all()

            # Обработка результатов
            zero_approval_campaigns = []
            total_wasted = 0
            total_pending_leads = 0

            for row in results:
                cost = float(row.total_cost)
                revenue = float(row.total_revenue)
                total_leads = int(row.total_leads)
                h_leads = int(row.total_h_leads)
                r_leads = int(row.total_r_leads)
                clicks = int(row.total_clicks)

                # Вычисляем метрики
                cr = (total_leads / clicks * 100) if clicks > 0 else 0
                cost_per_lead = cost / total_leads if total_leads > 0 else 0

                total_wasted += cost
                # Ожидающие лиды = hold лиды (или все лиды минус отклоненные, если hold нет)
                pending_leads = h_leads if h_leads > 0 else max(0, total_leads - r_leads)
                total_pending_leads += pending_leads

                # Определение критичности на основе превышения порога min_spend
                # Чем больше потрачено относительно порога, тем критичнее
                spend_multiplier = cost / min_spend if min_spend > 0 else 1

                if spend_multiplier >= severity_critical_threshold:
                    severity = "critical"
                elif spend_multiplier >= severity_high_threshold:
                    severity = "high"
                else:
                    severity = "medium"

                zero_approval_campaigns.append({
                    "campaign_id": row.internal_id,
                    "binom_id": row.binom_id,
                    "name": row.current_name,
                    "group": row.group_name or "Без группы",
                    "total_cost": cost,
                    "total_revenue": revenue,  # для таблицы
                    "avg_roi": round(((revenue - cost) / cost * 100) if cost > 0 else 0, 2),  # для таблицы
                    "total_leads": total_leads,
                    "h_leads": h_leads,
                    "r_leads": r_leads,
                    "cost_per_lead": round(cost_per_lead, 2),
                    "cr": round(cr, 2),
                    "severity": severity,
                    "total_clicks": clicks
                })

            # Сортировка по расходам (больше всего потрачено)
            zero_approval_campaigns.sort(key=lambda x: x['total_cost'], reverse=True)

            return {
                "campaigns": zero_approval_campaigns,
                "summary": {
                    "total_found": len(zero_approval_campaigns),
                    "total_wasted": round(total_wasted, 2),  # округляем до 2 знаков
                    "total_pending_leads": total_pending_leads,
                    "critical_count": sum(1 for c in zero_approval_campaigns if c['severity'] == 'critical'),
                    "high_count": sum(1 for c in zero_approval_campaigns if c['severity'] == 'high'),
                    "medium_count": sum(1 for c in zero_approval_campaigns if c['severity'] == 'medium')
                },
                "period_days": days,
                "thresholds": {
                    "min_leads": min_leads,
                    "min_spend": min_spend,
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
        campaigns = raw_data["campaigns"][:10]  # Топ-10

        if not campaigns:
            return []

        return [
            {
                "id": "leads_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in campaigns],
                    "datasets": [{
                        "label": "Количество лидов",
                        "data": [c["total_leads"] for c in campaigns],
                        "backgroundColor": "rgba(255, 206, 86, 0.5)",
                        "borderColor": "rgba(255, 206, 86, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Количество лидов без апрувов"
                        },
                        "legend": {
                            "display": False
                        }
                    },
                    "scales": {
                        "y": {
                            "beginAtZero": True
                        }
                    }
                }
            },
            {
                "id": "cost_chart",
                "type": "pie",
                "data": {
                    "labels": [c["name"][:25] for c in campaigns[:5]],
                    "datasets": [{
                        "data": [c["total_cost"] for c in campaigns[:5]],
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.8)",
                            "rgba(255, 159, 64, 0.8)",
                            "rgba(255, 205, 86, 0.8)",
                            "rgba(75, 192, 192, 0.8)",
                            "rgba(54, 162, 235, 0.8)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "Распределение расходов (Топ-5)"
                        }
                    }
                }
            }
        ]

    def generate_alerts(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Генерация критических алертов.
        Возвращает один общий алерт с краткой сводкой вместо множества алертов.
        """
        summary = raw_data["summary"]
        campaigns = raw_data["campaigns"]
        thresholds = raw_data.get("thresholds", {})
        alerts = []

        # Если есть кампании с нулевыми апрувами, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            total_wasted = summary["total_wasted"]
            total_pending_leads = summary["total_pending_leads"]
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]

            # Получаем пороги для сообщения
            severity_critical_threshold = thresholds.get("severity_critical", 5)
            min_spend = thresholds.get("min_spend", 10)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: {total_found} кампаний с 0% апрувом, потрачено: ${total_wasted:.2f}"
                if critical_count > 1:
                    message += f" (из них {critical_count} с расходом >{severity_critical_threshold}x от порога ${min_spend})"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: {total_found} кампаний с 0% апрувом, потрачено: ${total_wasted:.2f}"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} кампаний с 0% апрувом, потрачено: ${total_wasted:.2f}"

            message += f"\nВсего лидов без апрувов: {total_pending_leads}"

            # Добавляем краткую информацию о топ-3
            top_3 = campaigns[:3]
            if top_3:
                message += "\n\nТоп-3 по расходам:"
                for i, campaign in enumerate(top_3, 1):
                    message += f"\n{i}. {campaign['name']}: {campaign['total_leads']} лидов, потрачено ${campaign['total_cost']:.2f}"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Срочно проверьте качество трафика и настройки постбэка. Рассмотрите остановку критических кампаний"
            else:
                recommended_action = "Проверьте настройки постбэка и качество источников трафика"

            alerts.append({
                "type": "zero_approval_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "campaigns_count": total_found,
                "total_wasted": total_wasted,
                "critical_count": critical_count,
                "total_pending_leads": total_pending_leads
            })

        return alerts
