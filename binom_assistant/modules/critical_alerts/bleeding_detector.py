"""
Модуль поиска критически убыточных кампаний
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


class BleedingCampaignDetector(BaseModule):
    """
    Детектор убыточных кампаний.

    Находит кампании с критическим ROI за последние N дней.
    Критерии:
    - ROI < -50% (настраивается)
    - Минимум $5 трат (настраивается)
    - Период: 3 дня (настраивается)
    """

    def get_metadata(self) -> ModuleMetadata:
        """Возвращает метаданные модуля"""
        return ModuleMetadata(
            id="bleeding_detector",
            name="Утекающий бюджет",
            category="critical_alerts",
            description="Находит убыточные кампании с ROI < -50%",
            detailed_description="Модуль анализирует динамику ROI кампаний и выявляет те, которые начали резко терять деньги.",
            version="1.0.1",
            author="Binom Assistant",
            priority="critical",
            tags=["roi", "losses", "critical", "campaigns"]
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
                "roi_threshold": -50,  # ROI меньше -50%
                "min_spend": 5,  # минимум $5 трат
                "days": 3,  # за последние 3 дня
                "severity_critical": -70,  # ROI для critical severity
                "severity_high": -50  # ROI для high severity
            }
        )

    def get_param_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает метаданные параметров для UI"""
        return {
            "roi_threshold": {
                "label": "Порог ROI (%)",
                "description": "ROI ниже которого кампания считается убыточной",
                "type": "number",
                "min": -100,
                "max": 0,
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
            "metric": "roi",
            "metric_label": "ROI",
            "metric_unit": "%",
            "description": "Пороги критичности на основе ROI кампании",
            "thresholds": {
                "severity_critical": {
                    "label": "Критичный ROI",
                    "description": "ROI ниже этого значения считается критичным",
                    "type": "number",
                    "min": -100,
                    "max": 0,
                    "step": 5,
                    "default": -70
                },
                "severity_high": {
                    "label": "Высокий ROI",
                    "description": "ROI ниже этого значения (но выше критичного) считается высокой важности",
                    "type": "number",
                    "min": -100,
                    "max": 0,
                    "step": 5,
                    "default": -50
                }
            },
            "levels": [
                {"value": "critical", "label": "Критично", "color": "#ef4444", "condition": "ROI < critical"},
                {"value": "high", "label": "Высокий", "color": "#f59e0b", "condition": "critical <= ROI < high"},
                {"value": "medium", "label": "Средний", "color": "#3b82f6", "condition": "ROI >= high"}
            ]
        }

    def analyze(self, config: ModuleConfig) -> Dict[str, Any]:
        """
        Анализ убыточных кампаний через SQLAlchemy.

        Args:
            config: Конфигурация модуля

        Returns:
            Dict[str, Any]: Данные об убыточных кампаниях
        """
        # Получение параметров
        roi_threshold = config.params.get("roi_threshold", -50)
        min_spend = config.params.get("min_spend", 5)
        days = config.params.get("days", 3)

        # Получение настраиваемых порогов severity
        severity_critical_threshold = config.params.get("severity_critical", -70)
        severity_high_threshold = config.params.get("severity_high", -50)

        # Анализируем только полные дни (исключаем текущий неполный день)
        date_from = datetime.now().date() - timedelta(days=days)

        # Работа с БД
        with get_db_session() as session:
            # Запрос: агрегированная статистика по кампаниям за период
            # ROI вычисляется от суммарных показателей, а не как среднее по дням!
            query = session.query(
                Campaign.internal_id,
                Campaign.binom_id,
                Campaign.current_name,
                Campaign.group_name,
                func.sum(CampaignStatsDaily.cost).label('total_cost'),
                func.sum(CampaignStatsDaily.revenue).label('total_revenue'),
                func.sum(CampaignStatsDaily.clicks).label('total_clicks'),
                func.sum(CampaignStatsDaily.leads).label('total_leads')
            ).join(
                CampaignStatsDaily,
                Campaign.internal_id == CampaignStatsDaily.campaign_id
            ).filter(
                CampaignStatsDaily.date >= date_from,
                CampaignStatsDaily.cost > 0  # только активные
            ).group_by(
                Campaign.internal_id
            ).having(
                func.sum(CampaignStatsDaily.cost) >= min_spend
            )

            results = query.all()

            # Обработка результатов
            bleeding_campaigns = []
            total_losses = 0

            for row in results:
                cost = float(row.total_cost)
                revenue = float(row.total_revenue)
                loss = cost - revenue

                # Вычисляем правильный ROI от суммарных показателей
                if cost > 0:
                    roi = ((revenue - cost) / cost) * 100
                else:
                    roi = 0

                # Фильтруем только убыточные кампании (ROI < roi_threshold)
                if roi >= roi_threshold:
                    continue

                total_losses += loss

                # Определение критичности на основе настраиваемых порогов
                if roi < severity_critical_threshold:
                    severity = "critical"
                elif roi < severity_high_threshold:
                    severity = "high"
                else:
                    severity = "medium"

                bleeding_campaigns.append({
                    "campaign_id": row.internal_id,
                    "binom_id": row.binom_id,
                    "name": row.current_name,
                    "group": row.group_name or "Без группы",
                    "total_cost": cost,
                    "total_revenue": revenue,
                    "avg_roi": round(roi, 2),
                    "loss": loss,
                    "severity": severity,
                    "total_clicks": row.total_clicks,
                    "total_leads": row.total_leads
                })

            # Сортировка по убыткам
            bleeding_campaigns.sort(key=lambda x: x['loss'], reverse=True)

            return {
                "campaigns": bleeding_campaigns,
                "summary": {
                    "total_found": len(bleeding_campaigns),
                    "total_losses": total_losses,
                    "critical_count": sum(1 for c in bleeding_campaigns if c['severity'] == 'critical'),
                    "high_count": sum(1 for c in bleeding_campaigns if c['severity'] == 'high'),
                    "medium_count": sum(1 for c in bleeding_campaigns if c['severity'] == 'medium')
                },
                "period_days": days,
                "thresholds": {
                    "roi": roi_threshold,
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
                "id": "roi_chart",
                "type": "bar",
                "data": {
                    "labels": [c["name"][:30] for c in campaigns],
                    "datasets": [{
                        "label": "ROI (%)",
                        "data": [c["avg_roi"] for c in campaigns],
                        "backgroundColor": "rgba(255, 99, 132, 0.5)",
                        "borderColor": "rgba(255, 99, 132, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": "ROI убыточных кампаний"
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
            },
            {
                "id": "loss_chart",
                "type": "pie",
                "data": {
                    "labels": [c["name"][:25] for c in campaigns[:5]],
                    "datasets": [{
                        "data": [c["loss"] for c in campaigns[:5]],
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
                            "text": "Распределение убытков (Топ-5)"
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

        # Если есть убыточные кампании, создаем один общий алерт
        total_found = summary["total_found"]
        if total_found > 0:
            total_losses = summary["total_losses"]
            critical_count = summary["critical_count"]
            high_count = summary["high_count"]

            # Получаем порог для сообщения
            severity_critical_threshold = thresholds.get("severity_critical", -70)

            # Формируем сообщение
            if critical_count > 0:
                severity = "critical"
                message = f"КРИТИЧНО: {total_found} убыточных кампаний, общие убытки: ${total_losses:.2f}"
                if critical_count > 1:
                    message += f" (из них {critical_count} критических с ROI < {severity_critical_threshold}%)"
            elif high_count > 0:
                severity = "high"
                message = f"ВНИМАНИЕ: {total_found} убыточных кампаний, общие убытки: ${total_losses:.2f}"
            else:
                severity = "medium"
                message = f"ПРЕДУПРЕЖДЕНИЕ: {total_found} убыточных кампаний, общие убытки: ${total_losses:.2f}"

            # Добавляем краткую информацию о топ-3
            top_3 = campaigns[:3]
            if top_3:
                message += "\n\nТоп-3 убыточных:"
                for i, campaign in enumerate(top_3, 1):
                    message += f"\n{i}. {campaign['name']}: ROI {campaign['avg_roi']:.1f}%, убыток ${campaign['loss']:.2f}"

            # Рекомендуемое действие
            if critical_count > 0:
                recommended_action = "Проверьте критические кампании и остановите наиболее убыточные"
            else:
                recommended_action = "Проанализируйте убыточные кампании и примите решение о снижении бюджета"

            alerts.append({
                "type": "bleeding_campaigns_summary",
                "severity": severity,
                "message": message,
                "recommended_action": recommended_action,
                "campaigns_count": total_found,
                "total_losses": total_losses,
                "critical_count": critical_count
            })

        return alerts
