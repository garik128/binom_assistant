"""
Константы для работы с Binom API
"""

# Периоды дат для Binom API
# Используется в параметре date=X
PERIOD_TODAY = "1"              # Сегодня
PERIOD_YESTERDAY = "2"          # Вчера
PERIOD_LAST_7_DAYS = "3"        # Последние 7 дней
PERIOD_LAST_14_DAYS = "4"       # Последние 14 дней
PERIOD_CURRENT_MONTH = "5"      # Текущий месяц
PERIOD_LAST_MONTH = "6"         # Прошлый месяц
PERIOD_CUSTOM = "12"            # Произвольный период (требует date_s и date_e)
PERIOD_LAST_2_DAYS = "13"       # Последние 2 дня
PERIOD_LAST_3_DAYS = "14"       # Последние 3 дня

# Мапинг человекопонятных названий к кодам API
PERIOD_MAP = {
    'today': PERIOD_TODAY,
    'yesterday': PERIOD_YESTERDAY,
    '7days': PERIOD_LAST_7_DAYS,
    '14days': PERIOD_LAST_14_DAYS,
    '30days': PERIOD_CURRENT_MONTH,  # текущий месяц ~30 дней
    'current_month': PERIOD_CURRENT_MONTH,
    'last_month': PERIOD_LAST_MONTH,
    'custom': PERIOD_CUSTOM,
    '2days': PERIOD_LAST_2_DAYS,
    '3days': PERIOD_LAST_3_DAYS,
}

# Обратный мапинг (код API -> название)
PERIOD_NAME_MAP = {v: k for k, v in PERIOD_MAP.items()}

# Статусы кампаний
STATUS_ALL = 1              # Все кампании
STATUS_WITH_TRAFFIC = 2     # Только с трафиком за период
STATUS_ACTIVE = 3           # Только активные

# Группировки для статистики (параметр group1)
GROUP_BY_DATE = "31"        # По датам
GROUP_BY_SOURCE = "32"      # По источникам
GROUP_BY_COUNTRY = "33"     # По странам
GROUP_BY_LANDING = "34"     # По лендингам
GROUP_BY_OFFER = "35"       # По офферам
