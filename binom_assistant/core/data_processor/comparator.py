"""
Сравнение периодов и вычисление изменений
"""
import logging
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


def calculate_changes(
    current: Dict[str, Any],
    previous: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Вычисляет изменения между двумя периодами

    Args:
        current: данные текущего периода
        previous: данные предыдущего периода

    Returns:
        Словарь с изменениями
    """
    changes = {}

    # Метрики для сравнения
    metrics = ['clicks', 'leads', 'cost', 'revenue', 'profit', 'roi', 'cr', 'cpc']

    for metric in metrics:
        curr_value = float(current.get(metric, 0))
        prev_value = float(previous.get(metric, 0))

        # Абсолютное изменение
        absolute_change = curr_value - prev_value

        # Процентное изменение
        if prev_value != 0:
            percent_change = (curr_value - prev_value) / prev_value * 100
        else:
            # Если предыдущее значение = 0
            if curr_value > 0:
                percent_change = float('inf')  # Бесконечный рост
            elif curr_value < 0:
                percent_change = float('-inf')  # Бесконечное падение
            else:
                percent_change = 0  # Оба значения равны 0

        changes[metric] = {
            'current': curr_value,
            'previous': prev_value,
            'absolute': absolute_change,
            'percent': percent_change,
            'trend': 'up' if absolute_change > 0 else ('down' if absolute_change < 0 else 'stable')
        }

    return changes


def compare_periods(
    period1: Dict[str, Any],
    period2: Dict[str, Any],
    period1_name: str = "Period 1",
    period2_name: str = "Period 2"
) -> Dict[str, Any]:
    """
    Сравнивает два периода с детальной аналитикой

    Args:
        period1: данные первого периода
        period2: данные второго периода
        period1_name: название первого периода
        period2_name: название второго периода

    Returns:
        Словарь с результатами сравнения
    """
    changes = calculate_changes(period1, period2)

    # Определяем ключевые изменения
    key_insights = []

    # ROI изменился значительно?
    roi_change = changes['roi']['percent']
    if abs(roi_change) > 20:
        key_insights.append({
            'metric': 'ROI',
            'message': f"ROI {'вырос' if roi_change > 0 else 'упал'} на {abs(roi_change):.1f}%",
            'severity': 'high' if abs(roi_change) > 50 else 'medium'
        })

    # CR изменился значительно?
    cr_change = changes['cr']['percent']
    if abs(cr_change) > 30:
        key_insights.append({
            'metric': 'CR',
            'message': f"Конверсия {'выросла' if cr_change > 0 else 'упала'} на {abs(cr_change):.1f}%",
            'severity': 'high' if abs(cr_change) > 50 else 'medium'
        })

    # Расход значительно изменился?
    cost_change = changes['cost']['percent']
    if abs(cost_change) > 20:
        key_insights.append({
            'metric': 'Cost',
            'message': f"Расход {'вырос' if cost_change > 0 else 'снизился'} на {abs(cost_change):.1f}%",
            'severity': 'medium'
        })

    comparison = {
        'period1_name': period1_name,
        'period2_name': period2_name,
        'changes': changes,
        'key_insights': key_insights,
        'summary': _generate_summary(changes, period1_name, period2_name)
    }

    return comparison


def _generate_summary(
    changes: Dict[str, Any],
    period1_name: str,
    period2_name: str
) -> str:
    """Генерирует текстовую сводку"""
    roi_change = changes['roi']['percent']
    revenue_change = changes['revenue']['absolute']

    if roi_change > 10:
        summary = f"{period1_name} лучше {period2_name}: ROI вырос на {roi_change:.1f}%"
    elif roi_change < -10:
        summary = f"{period1_name} хуже {period2_name}: ROI упал на {abs(roi_change):.1f}%"
    else:
        summary = f"{period1_name} и {period2_name} примерно одинаковы"

    if revenue_change != 0:
        summary += f", доход изменился на ${abs(revenue_change):.2f}"

    return summary
