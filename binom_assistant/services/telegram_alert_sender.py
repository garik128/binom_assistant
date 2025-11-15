"""
Сервис для отправки алертов в Telegram
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramAlertSender:
    """
    Сервис для отправки алертов модулей в Telegram.
    Проверяет настройки и отправляет только разрешенные алерты.
    """

    def __init__(self):
        """Инициализация сервиса"""
        self.bot_token = None
        self.chat_id = None
        self._initialized = False

    def _ensure_initialized(self):
        """Ленивая инициализация бота"""
        if self._initialized:
            return

        try:
            import os

            # Получаем настройки из env
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')

            if not bot_token or not chat_id:
                logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in env")
                self._initialized = False
                return

            # Очищаем chat_id от возможного префикса (защита от ошибок в .env)
            chat_id_clean = chat_id.strip()
            if '=' in chat_id_clean:
                # Если есть '=', берем все после последнего '='
                chat_id_clean = chat_id_clean.split('=')[-1].strip()

            self.bot_token = bot_token
            self.chat_id = int(chat_id_clean)

            self._initialized = True
            logger.info("Telegram alert sender initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self._initialized = False

    def _get_enabled_modules(self) -> List[str]:
        """
        Получить список модулей, для которых включена отправка в Telegram

        Returns:
            Список ID модулей
        """
        try:
            from services.settings_manager import get_settings_manager

            settings = get_settings_manager()
            value = settings.get('telegram.alert_modules', default='[]')

            # Парсим JSON
            if isinstance(value, str):
                enabled_modules = json.loads(value)
            else:
                enabled_modules = value

            # По умолчанию только критические
            if not enabled_modules:
                enabled_modules = [
                    'bleeding_detector',
                    'zero_approval_alert',
                    'spend_spike_monitor',
                    'waste_campaign_finder',
                    'traffic_quality_crash',
                    'squeezed_offer'
                ]

            return enabled_modules

        except Exception as e:
            logger.error(f"Error getting enabled modules: {e}")
            # Возвращаем критические по умолчанию
            return [
                'bleeding_detector',
                'zero_approval_alert',
                'spend_spike_monitor',
                'waste_campaign_finder',
                'traffic_quality_crash',
                'squeezed_offer'
            ]

    def _escape_html(self, text: str) -> str:
        """
        Экранирует HTML символы для Telegram

        Args:
            text: Исходный текст

        Returns:
            Экранированный текст
        """
        import html
        return html.escape(text)

    def _escape_markdown(self, text: str) -> str:
        """
        Экранирует специальные символы для Markdown

        Args:
            text: Исходный текст

        Returns:
            Экранированный текст
        """
        # Символы которые нужно экранировать в Markdown
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, '\\' + char)
        return text

    def _get_module_names_mapping(self) -> Dict[str, str]:
        """
        Возвращает маппинг ID модулей на русские названия

        Returns:
            Словарь {module_id: russian_name}
        """
        return {
            # Критические алерты
            'bleeding_detector': 'Утекающий бюджет',
            'zero_approval_alert': 'Нет апрувов',
            'spend_spike_monitor': 'Всплеск расходов',
            'waste_campaign_finder': 'Слив бюджета',
            'traffic_quality_crash': 'Падение качества',
            'squeezed_offer': 'Отжатый оффер',

            # Анализ трендов
            'microtrend_scanner': 'Локальные тренды',
            'momentum_tracker': 'Сила импульса',
            'recovery_detector': 'Восстановление',
            'acceleration_monitor': 'Ускорение динамики',
            'trend_reversal_finder': 'Разворот тренда',

            # Стабильность
            'volatility_calculator': 'Колебания метрик',
            'consistency_scorer': 'Стабильность',
            'reliability_index': 'Надёжность',
            'performance_stability': 'Устойчивость результатов',

            # Предиктивная аналитика
            'roi_forecast': 'Прогноз окупаемости',
            'profitability_horizon': 'До безубыточности',
            'approval_rate_predictor': 'Прогноз апрувов',
            'campaign_lifecycle_stage': 'Этап кампании',
            'revenue_projection': 'Прогноз дохода',

            # Детекция проблем
            'sleepy_campaign_finder': 'Заснувшие кампании',
            'cpl_margin_monitor': 'Маржа CPL',
            'conversion_drop_alert': 'Падение конверсии',
            'approval_delay_impact': 'Задержка апрувов',
            'zombie_campaign_detector': 'Мёртвые кампании',
            'source_fatigue_detector': 'Выгорание источника',

            # Поиск возможностей
            'hidden_gems_finder': 'Скрытые точки роста',
            'sudden_winner_detector': 'Неожиданный лидер',
            'scaling_candidates': 'Готовы к росту',
            'breakout_alert': 'Прорыв',

            # Группировка
            'smart_consolidator': 'Умное объединение',
            'performance_segmenter': 'Сегменты эффективности',
            'source_group_matrix': 'Матрица групп',

            # Портфель
            'portfolio_health_index': 'Здоровье портфеля',
            'diversification_score': 'Диверсификация',
            'budget_optimizer': 'Оптимизация бюджета',
            'risk_assessment': 'Оценка рисков',
            'total_performance_tracker': 'Общая динамика',

            # Источники и офферы
            'offer_profitability_ranker': 'Рейтинг офферов',
            'source_quality_scorer': 'Качество источников',
            'network_performance_monitor': 'Эффективность сетей',
            'offer_lifecycle_tracker': 'Цикл оффера',
        }

    def _format_alert_message(self, module_id: str, alert: Dict[str, Any]) -> str:
        """
        Форматирует алерт для отправки в Telegram

        Args:
            module_id: ID модуля
            alert: Данные алерта

        Returns:
            Отформатированное сообщение в HTML
        """
        module_names = self._get_module_names_mapping()
        module_name = module_names.get(module_id, module_id)
        severity = alert.get('severity', 'medium')

        # Эмодзи по важности
        severity_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }
        emoji = severity_emoji.get(severity, '🔵')

        # Получаем базовый URL из env
        import os
        import re
        base_url = os.getenv('TELEGRAM_ALERT_BASE_URL', 'http://localhost:8000')

        # Валидация и санитизация module_id для предотвращения path traversal
        # Разрешаем только буквы, цифры, дефисы и подчеркивания
        safe_module_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(module_id))
        if not safe_module_id:
            safe_module_id = 'unknown'

        module_url = f"{base_url}/modules/{safe_module_id}"

        # Экранируем текст для HTML
        message_text = self._escape_html(alert.get('message', 'Нет описания'))
        module_name_escaped = self._escape_html(module_name)

        # Формируем сообщение в HTML
        lines = [
            f"{emoji} <b>{module_name_escaped}</b>",
            "",
            message_text
        ]

        if alert.get('recommended_action'):
            rec_action = self._escape_html(alert.get('recommended_action'))
            lines.append("")
            lines.append(f"💡 <b>Рекомендация:</b> {rec_action}")

        lines.append("")
        lines.append(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append("")
        # HTML link - кликабельная ссылка
        lines.append(f'<a href="{module_url}">Открыть модуль</a>')

        return "\n".join(lines)

    def _send_to_telegram(self, message: str):
        """
        Отправляет сообщение в Telegram через HTTP API

        Args:
            message: Текст сообщения в HTML формате
        """
        import httpx

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        # Логируем сообщение для отладки
        logger.debug(f"Sending to Telegram: {message[:200]}...")

        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=data)
                response.raise_for_status()
                logger.info(f"Telegram API response: {response.status_code}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Telegram API error: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error sending to Telegram API: {e}")
            return False

    def _format_batch_message(self, alerts_by_module: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        Форматирует сводное сообщение о множественных алертах

        Args:
            alerts_by_module: Словарь {module_id: [alerts]}

        Returns:
            Отформатированное сообщение в HTML
        """
        import os

        module_names = self._get_module_names_mapping()
        total_alerts = sum(len(alerts) for alerts in alerts_by_module.values())

        # Подсчитываем по критичности
        critical_count = 0
        high_count = 0
        medium_count = 0

        for alerts in alerts_by_module.values():
            for alert in alerts:
                severity = alert.get('severity', 'medium')
                if severity == 'critical':
                    critical_count += 1
                elif severity == 'high':
                    high_count += 1
                else:
                    medium_count += 1

        lines = [
            f"<b>Получено {total_alerts} новых алертов</b>",
            ""
        ]

        # Статистика по критичности
        if critical_count > 0:
            lines.append(f"🔴 Критичных: {critical_count}")
        if high_count > 0:
            lines.append(f"🟠 Высоких: {high_count}")
        if medium_count > 0:
            lines.append(f"🟡 Средних: {medium_count}")

        lines.append("")
        lines.append("<b>Модули с алертами:</b>")

        # Список модулей
        for module_id, alerts in sorted(alerts_by_module.items()):
            module_name = module_names.get(module_id, module_id)
            module_name_escaped = self._escape_html(module_name)

            # Подсчет критичности для модуля
            module_critical = sum(1 for a in alerts if a.get('severity') == 'critical')
            module_high = sum(1 for a in alerts if a.get('severity') == 'high')

            if module_critical > 0:
                emoji = '🔴'
            elif module_high > 0:
                emoji = '🟠'
            else:
                emoji = '🟡'

            count_text = f"({len(alerts)})" if len(alerts) > 1 else ""
            lines.append(f"{emoji} {module_name_escaped} {count_text}")

        lines.append("")
        lines.append(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")

        # Ссылка на страницу алертов
        base_url = os.getenv('TELEGRAM_ALERT_BASE_URL', 'http://localhost:8000')
        alerts_url = f"{base_url}/alerts"
        lines.append("")
        lines.append(f'<a href="{alerts_url}">Смотреть все алерты</a>')

        return "\n".join(lines)

    def send_alerts(self, module_id: str, alerts: List[Dict[str, Any]]):
        """
        Отправка алертов в Telegram

        Args:
            module_id: ID модуля
            alerts: Список алертов
        """
        if not alerts:
            logger.debug(f"No alerts to send for module '{module_id}'")
            return

        # Инициализируем бота
        self._ensure_initialized()
        if not self._initialized or not self.bot_token:
            logger.warning("Telegram bot not initialized, skipping alerts")
            return

        # Проверяем, включен ли модуль
        enabled_modules = self._get_enabled_modules()
        if module_id not in enabled_modules:
            logger.debug(f"Module {module_id} not enabled for Telegram alerts")
            return

        # Стратегия отправки:
        # - Если 1-3 алерта - отправляем каждый отдельно
        # - Если > 3 алертов - отправляем батчем (одно сводное сообщение)

        if len(alerts) <= 3:
            # Отправляем по отдельности
            import time
            for alert in alerts:
                try:
                    message = self._format_alert_message(module_id, alert)
                    if self._send_to_telegram(message):
                        logger.info(f"Sent alert from {module_id} to Telegram: {alert.get('type', 'unknown')}")
                        time.sleep(1)  # Rate limiting: 1 секунда между сообщениями
                except Exception as e:
                    logger.error(f"Error sending alert to Telegram: {e}")
                    continue
        else:
            # Отправляем батчем
            try:
                alerts_by_module = {module_id: alerts}
                message = self._format_batch_message(alerts_by_module)
                if self._send_to_telegram(message):
                    logger.info(f"Sent batch of {len(alerts)} alerts from {module_id} to Telegram")
            except Exception as e:
                logger.error(f"Error sending batch alert to Telegram: {e}")


# Глобальный экземпляр
_telegram_alert_sender = None


def get_telegram_alert_sender() -> TelegramAlertSender:
    """
    Получить глобальный экземпляр отправителя алертов

    Returns:
        TelegramAlertSender
    """
    global _telegram_alert_sender
    if _telegram_alert_sender is None:
        _telegram_alert_sender = TelegramAlertSender()
    return _telegram_alert_sender
