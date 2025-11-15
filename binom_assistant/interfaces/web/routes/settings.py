# -*- coding: utf-8 -*-
"""
API endpoints для управления настройками приложения
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from pydantic import BaseModel
from ..auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


class SettingUpdate(BaseModel):
    """Модель для обновления настройки"""
    value: Any
    value_type: str = None
    description: str = None


@router.get("/settings")
async def get_all_settings() -> Dict[str, Any]:
    """
    Получает все настройки из БД

    Returns:
        Словарь со всеми настройками
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        all_settings = settings.get_all()

        return {
            "status": "ok",
            "settings": all_settings
        }

    except Exception as e:
        logger.error(f"Error getting all settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/{key}")
async def get_setting(key: str) -> Dict[str, Any]:
    """
    Получает конкретную настройку

    Args:
        key: ключ настройки (например, collector.update_days)

    Returns:
        Значение настройки с метаданными
    """
    try:
        from services.settings_manager import get_settings_manager
        from storage.database import session_scope, AppSettings

        settings = get_settings_manager()
        value = settings.get(key)

        # Получаем детали из БД
        with session_scope() as session:
            setting = session.query(AppSettings).filter_by(key=key).first()
            if setting:
                return {
                    "status": "ok",
                    "setting": setting.to_dict()
                }

        # Если в БД нет, возвращаем только значение
        return {
            "status": "ok",
            "setting": {
                "key": key,
                "value": value,
                "source": "env_or_default"
            }
        }

    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/category/{category}")
async def get_settings_by_category(category: str) -> Dict[str, Any]:
    """
    Получает все настройки определенной категории с детальной информацией

    Args:
        category: категория (collector, schedule, filters, etc)

    Returns:
        Список настроек с метаданными
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        category_settings = settings.get_category_details(category)

        return {
            "status": "ok",
            "category": category,
            "settings": category_settings
        }

    except Exception as e:
        logger.error(f"Error getting category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def validate_setting_value(key: str, value: Any) -> Any:
    """
    Валидирует значение настройки в зависимости от её ключа.

    Args:
        key: Ключ настройки
        value: Значение для валидации

    Returns:
        Валидированное и приведенное к правильному типу значение

    Raises:
        HTTPException: Если значение невалидно
    """
    # Правила валидации для известных ключей
    validation_rules = {
        'collector.update_days': {'type': int, 'min': 1, 'max': 365},
        'collector.interval_hours': {'type': int, 'min': 1, 'max': 24},
        'chat.max_history_messages': {'type': int, 'min': 5, 'max': 100},
        'chat.max_stored_sessions': {'type': int, 'min': 10, 'max': 1000},
        'collector.enabled': {'type': bool},
        # schedule.daily_stats и schedule.weekly_stats - это cron строки, не bool!
    }

    rule = validation_rules.get(key)
    if not rule:
        # Для неизвестных ключей просто возвращаем как есть
        return value

    # Приводим к нужному типу
    expected_type = rule['type']
    try:
        if expected_type == bool:
            # Для bool принимаем разные форматы
            if isinstance(value, bool):
                typed_value = value
            elif isinstance(value, str):
                typed_value = value.lower() in ('true', '1', 'yes', 'on')
            else:
                typed_value = bool(value)
        elif expected_type == int:
            typed_value = int(value)
        elif expected_type == float:
            typed_value = float(value)
        else:
            typed_value = expected_type(value)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type for {key}. Expected {expected_type.__name__}: {e}"
        )

    # Проверяем диапазон для числовых значений
    if 'min' in rule and typed_value < rule['min']:
        raise HTTPException(
            status_code=400,
            detail=f"Value {typed_value} for {key} is too small. Minimum: {rule['min']}"
        )
    if 'max' in rule and typed_value > rule['max']:
        raise HTTPException(
            status_code=400,
            detail=f"Value {typed_value} for {key} is too large. Maximum: {rule['max']}"
        )

    return typed_value


@router.put("/settings/{key}")
async def update_setting(key: str, update: SettingUpdate) -> Dict[str, Any]:
    """
    Обновляет настройку в БД

    Args:
        key: ключ настройки
        update: новые данные

    Returns:
        Результат обновления
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()

        # Валидируем значение
        validated_value = validate_setting_value(key, update.value)

        success = settings.set(
            key=key,
            value=validated_value,
            value_type=update.value_type,
            description=update.description
        )

        if success:
            # Очищаем кэш
            settings.clear_cache()

            return {
                "status": "ok",
                "message": f"Setting {key} updated successfully",
                "new_value": validated_value
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update setting")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/{key}")
async def reset_setting(key: str) -> Dict[str, Any]:
    """
    Удаляет настройку из БД (fallback на .env или default)

    Args:
        key: ключ настройки

    Returns:
        Результат удаления
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        success = settings.reset(key)

        if success:
            # Получаем новое значение после reset
            new_value = settings.get(key)

            return {
                "status": "ok",
                "message": f"Setting {key} reset to default",
                "new_value": new_value
            }
        else:
            return {
                "status": "warning",
                "message": f"Setting {key} not found in DB, already using default"
            }

    except Exception as e:
        logger.error(f"Error resetting setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/migrate-from-env")
async def migrate_from_env(keys: List[str] = None) -> Dict[str, Any]:
    """
    Мигрирует настройки из .env в БД

    Args:
        keys: список ключей для миграции (опционально, по умолчанию все)

    Returns:
        Количество мигрированных настроек
    """
    try:
        from services.settings_manager import get_settings_manager

        if keys is None:
            # Дефолтные ключи для миграции
            keys = [
                'collector.update_days',
                'collector.interval_hours',
                'schedule.daily_stats',
                'schedule.weekly_stats'
            ]

        settings = get_settings_manager()
        migrated = settings.migrate_from_env(keys)

        return {
            "status": "ok",
            "message": f"Migrated {migrated} settings from .env to DB",
            "migrated_count": migrated
        }

    except Exception as e:
        logger.error(f"Error migrating from env: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TelegramAlertsSettings(BaseModel):
    """Модель настроек Telegram алертов"""
    enabled_modules: List[str]


@router.get("/settings/telegram/alerts")
async def get_telegram_alerts_settings() -> Dict[str, Any]:
    """
    Получить настройки уведомлений Telegram для алертов

    Returns:
        Список включенных модулей
    """
    try:
        from services.settings_manager import get_settings_manager

        settings = get_settings_manager()
        value = settings.get('telegram.alert_modules', default='[]')

        # Парсим JSON
        import json
        try:
            enabled_modules = json.loads(value) if isinstance(value, str) else value
        except:
            # По умолчанию включены только критические
            enabled_modules = [
                'bleeding_detector',
                'zero_approval_alert',
                'spend_spike_monitor',
                'waste_campaign_finder',
                'traffic_quality_crash',
                'squeezed_offer'
            ]

        return {
            "status": "ok",
            "settings": enabled_modules
        }

    except Exception as e:
        logger.error(f"Error getting telegram alerts settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/telegram/alerts")
async def save_telegram_alerts_settings(
    data: TelegramAlertsSettings
) -> Dict[str, Any]:
    """
    Сохранить настройки уведомлений Telegram для алертов

    Args:
        data: Настройки с списком включенных модулей

    Returns:
        Статус сохранения
    """
    try:
        from services.settings_manager import get_settings_manager
        import json

        settings = get_settings_manager()

        # Сохраняем как JSON
        success = settings.set(
            key='telegram.alert_modules',
            value=json.dumps(data.enabled_modules),
            value_type='json',
            description='Список модулей для отправки алертов в Telegram'
        )

        if success:
            logger.info(f"Saved telegram alerts settings: {len(data.enabled_modules)} modules enabled")

            return {
                "status": "ok",
                "message": "Настройки сохранены",
                "enabled_count": len(data.enabled_modules)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save settings")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving telegram alerts settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
