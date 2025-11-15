/**
 * Основной JavaScript файл Binom Assistant
 */

// ========== Проверка авторизации ========== //

// Проверяем авторизацию сразу при загрузке скрипта
// Это должно сработать до отрисовки страницы
(function() {
    // Пропускаем проверку только для страницы логина
    if (window.location.pathname === '/api/v1/auth/login') {
        return;
    }

    // Проверяем наличие токена напрямую из localStorage
    const token = localStorage.getItem('access_token');
    console.log('[AUTH CHECK] Token present:', !!token, 'Path:', window.location.pathname);

    if (!token) {
        console.log('[AUTH CHECK] No token found, redirecting to login');
        // Редирект на логин
        window.location.href = '/api/v1/auth/login';
        return;
    }

    // Проверяем валидность токена
    try {
        // Декодируем JWT чтобы проверить expiration
        const payload = JSON.parse(atob(token.split('.')[1]));
        const now = Math.floor(Date.now() / 1000);

        if (payload.exp && payload.exp < now) {
            console.log('[AUTH CHECK] Token expired, redirecting to login');
            localStorage.removeItem('access_token');
            window.location.href = '/api/v1/auth/login';
        }
    } catch (e) {
        console.error('[AUTH CHECK] Failed to parse token:', e);
        // Если токен невалидный - удаляем и редиректим
        localStorage.removeItem('access_token');
        window.location.href = '/api/v1/auth/login';
    }
})();

// ========== Утилиты ========== //

/**
 * Toast уведомления
 */
const toast = {
    show(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toastEl = document.createElement('div');
        toastEl.className = `toast ${type}`;
        toastEl.innerHTML = `
            <div>${message}</div>
        `;

        container.appendChild(toastEl);

        setTimeout(() => {
            toastEl.style.opacity = '0';
            setTimeout(() => toastEl.remove(), 300);
        }, 3000);
    },

    success(message) {
        this.show(message, 'success');
    },

    error(message) {
        this.show(message, 'error');
    },

    warning(message) {
        this.show(message, 'warning');
    },

    info(message) {
        this.show(message, 'info');
    }
};

window.toast = toast;

/**
 * Кэш для данных
 */
const cache = {
    // Префикс для ключей кеша
    prefix: 'cache_',

    set(key, value, ttl = 300000) { // 5 минут по умолчанию
        const item = {
            value,
            expiry: Date.now() + ttl
        };
        localStorage.setItem(this.prefix + key, JSON.stringify(item));
    },

    get(key) {
        const itemStr = localStorage.getItem(this.prefix + key);
        if (!itemStr) return null;

        const item = JSON.parse(itemStr);
        if (Date.now() > item.expiry) {
            localStorage.removeItem(this.prefix + key);
            return null;
        }

        return item.value;
    },

    clear() {
        // ИСПРАВЛЕНО: удаляем только ключи кеша, НЕ трогаем access_token и theme!
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith(this.prefix)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log(`[CACHE] Cleared ${keysToRemove.length} cache entries, preserved access_token and theme`);
    }
};

window.cache = cache;

/**
 * Форматирование чисел
 */
const formatters = {
    number(num) {
        return new Intl.NumberFormat('ru-RU').format(num);
    },

    currency(num) {
        return new Intl.NumberFormat('ru-RU', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2
        }).format(num);
    },

    percent(num) {
        return new Intl.NumberFormat('ru-RU', {
            style: 'percent',
            minimumFractionDigits: 2
        }).format(num / 100);
    },

    date(dateStr) {
        const date = new Date(dateStr);
        return new Intl.DateTimeFormat('ru-RU').format(date);
    },

    time(dateStr) {
        const date = new Date(dateStr);
        return new Intl.DateTimeFormat('ru-RU', {
            hour: '2-digit',
            minute: '2-digit'
        }).format(date);
    }
};

window.formatters = formatters;

// ========== Управление UI ========== //

/**
 * Управление навигацией (бывший сайдбар)
 */
function initNavigation() {
    const menuToggle = document.getElementById('menuToggle');
    const headerNav = document.querySelector('.header-nav');

    if (menuToggle) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            // На мобильных - открываем/закрываем навигацию
            if (window.innerWidth <= 768) {
                document.body.classList.toggle('mobile-nav-open');
            }
        });
    }

    // Закрытие навигации при клике вне её (мобильные)
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 &&
            document.body.classList.contains('mobile-nav-open') &&
            headerNav &&
            !headerNav.contains(e.target) &&
            !menuToggle.contains(e.target)) {
            document.body.classList.remove('mobile-nav-open');
        }
    });

    // Закрытие навигации при клике на пункт меню (мобильные)
    if (headerNav) {
        const navItems = headerNav.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', () => {
                if (window.innerWidth <= 768) {
                    document.body.classList.remove('mobile-nav-open');
                }
            });
        });
    }

    // Устанавливаем активный пункт меню на основе текущего URL
    setActiveNavItem();
}

/**
 * Устанавливает активный пункт меню на основе текущего URL
 */
function setActiveNavItem() {
    const currentPath = window.location.pathname;
    const navItems = document.querySelectorAll('.nav-item[data-page]');

    // Убираем класс active у всех пунктов
    navItems.forEach(item => item.classList.remove('active'));

    // Определяем активный пункт на основе URL
    let activePage = null;

    if (currentPath === '/' || currentPath === '/index' || currentPath === '/dashboard') {
        activePage = 'dashboard';
    } else if (currentPath.startsWith('/analytics') || currentPath.startsWith('/modules/')) {
        activePage = 'analytics';
    } else if (currentPath.startsWith('/alerts')) {
        activePage = 'alerts';
    } else if (currentPath.startsWith('/chat')) {
        activePage = 'chat';
    } else if (currentPath.startsWith('/settings')) {
        activePage = 'settings';
    }

    // Находим и активируем соответствующий пункт меню (только если activePage определена)
    if (activePage) {
        const activeItem = document.querySelector(`.nav-item[data-page="${activePage}"]`);
        if (activeItem) {
            activeItem.classList.add('active');
        }
    }
}

/**
 * Управление лоадером
 */
function hideLoader() {
    const loader = document.getElementById('initial-loader');
    if (loader) {
        loader.classList.add('hidden');
    }
}

function showLoader() {
    const loader = document.getElementById('initial-loader');
    if (loader) {
        loader.classList.remove('hidden');
    }
}

window.hideLoader = hideLoader;
window.showLoader = showLoader;

/**
 * Обновление времени последнего обновления
 */
async function updateLastUpdateTime() {
    const timeEl = document.getElementById('lastUpdateTime');
    if (!timeEl) return;

    try {
        const status = await api.get('/system/refresh/status');

        // Проверяем, идет ли сейчас обновление данных
        if (status.is_updating) {
            // Показываем статус обновления
            if (status.update_progress !== null && status.update_progress !== undefined) {
                timeEl.textContent = `Обновление... (${status.update_progress}%)`;
            } else {
                timeEl.textContent = 'Обновление...';
            }

            // Опционально: добавляем tooltip с подробным сообщением
            if (status.update_message) {
                timeEl.title = status.update_message;
            }
        } else if (status.last_stat_update) {
            const updateTime = new Date(status.last_stat_update);

            // Форматируем дату и время
            const dateStr = formatters.date(updateTime);
            const timeStr = formatters.time(updateTime);

            timeEl.textContent = `${dateStr} ${timeStr}`;
            timeEl.title = ''; // Очищаем tooltip
        } else {
            timeEl.textContent = 'Нет данных';
            timeEl.title = '';
        }
    } catch (error) {
        console.error('Error getting last update time:', error);
        // В случае ошибки показываем текущее время
        const now = new Date();
        timeEl.textContent = formatters.time(now);
    }
}

/**
 * Проверка состояния системы и обновление индикатора
 * С exponential backoff при повторяющихся ошибках
 */
let healthCheckFailCount = 0;
let healthCheckAbortController = null;

async function updateSystemStatus() {
    const statusDot = document.getElementById('systemStatusDot');
    const uptimeEl = document.getElementById('systemUptime');
    if (!statusDot) return;

    // Отменяем предыдущий запрос если он еще выполняется
    if (healthCheckAbortController) {
        healthCheckAbortController.abort();
    }

    // Создаем новый AbortController
    healthCheckAbortController = new AbortController();

    try {
        // Используем более короткий таймаут для health check
        const health = await api.get('/system/health', 10000);

        // Сброс счетчика ошибок при успешном запросе
        if (healthCheckFailCount > 0) {
            console.log(`[Health Check] Recovered after ${healthCheckFailCount} failures`);
        }
        healthCheckFailCount = 0;
        healthCheckAbortController = null;

        // Убираем все классы статуса
        statusDot.classList.remove('status-online', 'status-warning', 'status-error');

        // Добавляем нужный класс
        if (health.status === 'ok') {
            statusDot.classList.add('status-online');
        } else if (health.status === 'warning') {
            statusDot.classList.add('status-warning');
        } else {
            statusDot.classList.add('status-error');
        }

        // Формируем детальный tooltip с информацией по компонентам
        let tooltipText = health.message;

        if (health.components && Object.keys(health.components).length > 0) {
            tooltipText += '\n\n';
            const icons = {
                'ok': '\u2713',
                'warning': '\u26A0',
                'error': '\u2717',
                'not_configured': '\u2022'
            };

            for (const [key, component] of Object.entries(health.components)) {
                const icon = icons[component.status] || '\u2022';
                tooltipText += `${icon} ${component.message}\n`;
            }
        }

        statusDot.title = tooltipText.trim();

        // Обновляем uptime
        if (uptimeEl && health.uptime) {
            uptimeEl.textContent = health.uptime.uptime_formatted || 'N/A';
            uptimeEl.title = `Запущен: ${health.uptime.started_at ? new Date(health.uptime.started_at).toLocaleString('ru-RU') : 'N/A'}`;
        }

    } catch (error) {
        // Игнорируем ошибки отмены запроса
        if (error.name === 'AbortError') {
            return;
        }

        healthCheckFailCount++;
        healthCheckAbortController = null;

        // Логируем только первую ошибку и каждую 10-ю, чтобы не засорять консоль
        if (healthCheckFailCount === 1 || healthCheckFailCount % 10 === 0) {
            console.warn(`[Health Check] Failed (attempt ${healthCheckFailCount}):`, error.message);
        }

        // В случае ошибки показываем error статус
        statusDot.classList.remove('status-online', 'status-warning', 'status-error');
        statusDot.classList.add('status-error');
        statusDot.title = `Не удалось получить статус системы (ошибок: ${healthCheckFailCount})`;

        if (uptimeEl) {
            uptimeEl.textContent = 'N/A';
            uptimeEl.title = 'Статус недоступен';
        }
    }
}

/**
 * Глобальный поиск (ОТКЛЮЧЕНО - поле поиска убрано из header)
 */
// function initGlobalSearch() {
//     const searchInput = document.getElementById('globalSearch');
//     if (!searchInput) return;
//
//     let searchTimeout;
//     searchInput.addEventListener('input', (e) => {
//         clearTimeout(searchTimeout);
//         const query = e.target.value.trim();
//
//         if (query.length < 2) return;
//
//         searchTimeout = setTimeout(async () => {
//             try {
//                 const results = await api.get(`/campaigns/search?q=${encodeURIComponent(query)}`);
//                 // Показать результаты поиска
//                 console.log('Search results:', results);
//             } catch (error) {
//                 console.error('Search error:', error);
//             }
//         }, 300);
//     });
// }

/**
 * Кнопки в хедере
 */
function initHeaderButtons() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            // Анимация вращения кнопки
            refreshBtn.classList.add('rotating');
            refreshBtn.disabled = true;

            try {
                toast.info('Запуск обновления данных из Binom...');

                // Запускаем обновление и получаем task_id
                const response = await api.post('/system/refresh');
                const taskId = response.task_id;

                if (!taskId) {
                    throw new Error('Task ID not received');
                }

                toast.success('Обновление запущено, отслеживаем прогресс...');

                // Функция проверки прогресса задачи
                const checkTaskProgress = async () => {
                    try {
                        const task = await api.get(`/system/tasks/${taskId}`);

                        // Обновляем индикатор прогресса
                        if (task.progress !== undefined) {
                            const progressText = `${task.progress}% - ${task.progress_message || 'Обработка...'}`;
                            console.log('Progress:', progressText);

                            // Показываем прогресс в toast (каждые 20%)
                            if (task.progress % 20 === 0 && task.progress > 0 && task.progress < 100) {
                                toast.info(progressText);
                            }
                        }

                        // Проверяем статус
                        if (task.status === 'completed') {
                            clearInterval(checkInterval);
                            refreshBtn.classList.remove('rotating');
                            refreshBtn.disabled = false;

                            const result = task.result || {};
                            toast.success(`Обновление завершено! Кампаний: ${result.campaigns || 0}, источников: ${result.traffic_sources || 0}`);

                            // Обновляем данные на странице
                            cache.clear();
                            if (typeof loadStats === 'function') loadStats();
                            if (typeof loadTopCampaigns === 'function') loadTopCampaigns();
                            if (typeof loadRecentAlerts === 'function') loadRecentAlerts();
                            if (typeof loadCharts === 'function') loadCharts();
                            updateLastUpdateTime();
                            updateSystemStatus();

                        } else if (task.status === 'failed') {
                            clearInterval(checkInterval);
                            refreshBtn.classList.remove('rotating');
                            refreshBtn.disabled = false;

                            toast.error(`Ошибка обновления: ${task.error || 'Неизвестная ошибка'}`);
                        }

                    } catch (error) {
                        console.error('Error checking task progress:', error);
                        // Не останавливаем проверку при ошибке, продолжаем попытки
                    }
                };

                // Проверяем прогресс каждые 5 секунд
                const checkInterval = setInterval(checkTaskProgress, 5000);

                // Первая проверка сразу
                checkTaskProgress();

                // Останавливаем проверку через 2 часа (на случай если что-то пошло не так)
                setTimeout(() => {
                    clearInterval(checkInterval);
                    if (refreshBtn.disabled) {
                        refreshBtn.classList.remove('rotating');
                        refreshBtn.disabled = false;
                        toast.warning('Проверка прогресса остановлена (таймаут 2 часа)');
                    }
                }, 7200000); // 2 часа

            } catch (error) {
                console.error('Refresh error:', error);
                toast.error('Ошибка при запуске обновления: ' + (error.message || 'Неизвестная ошибка'));
                refreshBtn.classList.remove('rotating');
                refreshBtn.disabled = false;
            }
        });
    }

    // Инициализация системы уведомлений
    if (typeof initNotifications === 'function') {
        initNotifications();
    }

    // Кнопка настроек удалена, теперь это пункт в навигации
}

// ========== Инициализация ========== //

/**
 * Обновляет tooltip кнопки refresh с актуальным периодом
 */
async function updateRefreshButtonTooltip() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (!refreshBtn) return;

    try {
        const config = await api.get('/system/config');
        const days = config.update_days || 7;
        refreshBtn.title = `Обновить данные за последние ${days} дней из Binom`;
    } catch (error) {
        console.error('Error updating refresh button tooltip:', error);
        // Оставляем дефолтный текст
    }
}

/**
 * Проверяет и восстанавливает отслеживание активных фоновых задач
 * С адаптивным интервалом проверки
 */
async function checkAndResumeActiveTasks() {
    let checkAttempts = 0;
    const maxCheckAttempts = 6; // Уменьшено с 12 до 6 попыток
    let checkInterval = 3000; // Начальный интервал 3 секунды (вместо 5)

    const performCheck = async () => {
        try {
            checkAttempts++;
            const response = await api.get('/system/tasks/active', 10000); // 10 секунд таймаут
            const activeTasks = response.tasks || [];

            if (activeTasks.length === 0) {
                // Логируем только каждую 3-ю попытку, чтобы не спамить
                if (checkAttempts % 3 === 1 || checkAttempts === maxCheckAttempts) {
                    console.log(`[Task Check] No active tasks (attempt ${checkAttempts}/${maxCheckAttempts})`);
                }

                // Если задач нет и это не первая попытка
                if (checkAttempts < maxCheckAttempts) {
                    // Увеличиваем интервал после 3-й попытки (3s -> 5s -> 10s)
                    if (checkAttempts >= 3) {
                        checkInterval = Math.min(checkInterval * 1.5, 10000);
                    }
                    return false; // Продолжаем периодическую проверку
                }
                console.log('[Task Check] Stopping periodic check - no active tasks found');
                return true; // Останавливаем проверку
            }

            // Ищем initial_collection или data_collection задачи
            const dataCollectionTask = activeTasks.find(t =>
                t.task_type === 'initial_collection' || t.task_type === 'data_collection'
            );

            if (dataCollectionTask) {
                const refreshBtn = document.getElementById('refreshBtn');
                if (!refreshBtn) return true;

                // Показываем модалку для initial_collection
                if (dataCollectionTask.task_type === 'initial_collection') {
                    openFirstRunModal();
                }

                // Активируем анимацию кнопки
                refreshBtn.classList.add('rotating');
                refreshBtn.disabled = true;

                // Запускаем отслеживание прогресса
                const checkInterval = setInterval(async () => {
                    try {
                        const task = await api.get(`/system/tasks/${dataCollectionTask.id}`);

                        // Показываем прогресс в консоли
                        if (task.progress_message && task.progress > 0) {
                            console.log(`Task progress: ${task.progress}% - ${task.progress_message}`);
                        }

                        // Проверяем статус
                        if (task.status === 'completed') {
                            clearInterval(checkInterval);
                            refreshBtn.classList.remove('rotating');
                            refreshBtn.disabled = false;

                            const result = task.result || {};
                            const message = dataCollectionTask.task_type === 'initial_collection'
                                ? `Первичный сбор данных завершен! Кампаний: ${result.campaigns || 0}`
                                : `Обновление завершено! Кампаний: ${result.campaigns || 0}`;

                            // Для initial_collection проверяем, открыта ли модалка
                            if (dataCollectionTask.task_type === 'initial_collection') {
                                const modal = document.getElementById('firstRunModal');
                                const modalIsOpen = modal && modal.style.display === 'block';

                                if (modalIsOpen) {
                                    // Модалка открыта - закрываем и перезагружаем страницу
                                    closeFirstRunModal();
                                    toast.success(message + ' - Перезагружаем страницу...');

                                    setTimeout(() => {
                                        location.reload();
                                    }, 1500); // 1.5 секунды задержка для показа toast

                                    return; // Выходим, не обновляем данные вручную
                                } else {
                                    // Модалка закрыта (пользователь закрыл вручную) - просто обновляем данные
                                    toast.success(message);
                                }
                            } else {
                                // Для обычного обновления - просто toast
                                toast.success(message);
                            }

                            // Обновляем данные на странице (только если не перезагружаем)
                            if (typeof loadDashboardData === 'function') {
                                loadDashboardData();
                            }
                            if (typeof loadTopCampaigns === 'function') {
                                loadTopCampaigns();
                            }
                            updateLastUpdateTime();
                            updateSystemStatus();

                        } else if (task.status === 'failed') {
                            clearInterval(checkInterval);
                            refreshBtn.classList.remove('rotating');
                            refreshBtn.disabled = false;

                            // Закрываем модалку для initial_collection
                            if (dataCollectionTask.task_type === 'initial_collection') {
                                closeFirstRunModal();
                            }

                            toast.error(`Ошибка: ${task.error || 'Неизвестная ошибка'}`);
                        }

                    } catch (error) {
                        console.error('Error checking task:', error);
                    }
                }, 5000); // Проверяем каждые 5 секунд

                // Останавливаем проверку через 2 часа (таймаут)
                setTimeout(() => {
                    clearInterval(checkInterval);
                    if (refreshBtn.disabled) {
                        refreshBtn.classList.remove('rotating');
                        refreshBtn.disabled = false;

                        // Закрываем модалку если открыта
                        if (dataCollectionTask.task_type === 'initial_collection') {
                            closeFirstRunModal();
                        }

                        toast.warning('Проверка прогресса остановлена (таймаут 2 часа)');
                    }
                }, 7200000); // 2 часа

                return true; // Останавливаем периодическую проверку
            }

            return true; // Останавливаем проверку

        } catch (error) {
            console.error('Error checking active tasks:', error);
            return checkAttempts >= maxCheckAttempts; // Продолжаем пока не достигнем лимита
        }
    };

    // Рекурсивная функция для периодической проверки с переменным интервалом
    const scheduleNextCheck = async () => {
        const shouldStop = await performCheck();

        if (!shouldStop) {
            // Запускаем следующую проверку с актуальным интервалом
            setTimeout(scheduleNextCheck, checkInterval);
        }
    };

    // Первая проверка с задержкой 2 секунды
    setTimeout(scheduleNextCheck, 2000);
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Binom Assistant initialized');

    initNavigation();
    initHeaderButtons();

    // Скрываем лоадер после загрузки
    setTimeout(hideLoader, 500);

    // Обновляем время последнего обновления БД
    updateLastUpdateTime();

    // Проверяем статус системы
    updateSystemStatus();

    // Обновляем tooltip кнопки refresh
    updateRefreshButtonTooltip();

    // Проверяем активные задачи и восстанавливаем отслеживание
    checkAndResumeActiveTasks();

    // Периодическая проверка статуса (каждые 30 секунд)
    setInterval(updateSystemStatus, 30000);

    // Периодическое обновление времени последнего обновления (каждые 10 секунд)
    // Чаще чем статус, чтобы отслеживать прогресс обновления
    setInterval(updateLastUpdateTime, 10000);

    // Инициализация модалки доната
    initDonateModal();
});

// ========== Donate Modal ========== //

/**
 * Инициализация модалки доната
 */
function initDonateModal() {
    const modal = document.getElementById('donateModal');
    if (!modal) return;

    // Открытие модалки по клику на ссылку #donate
    document.addEventListener('click', (e) => {
        if (e.target.closest('a[href="#donate"]')) {
            e.preventDefault();
            openDonateModal();
        }
    });

    // Закрытие модалки при клике на фон
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeDonateModal();
        }
    });

    // Закрытие по Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('show')) {
            closeDonateModal();
        }
    });
}

/**
 * Открыть модалку доната
 */
function openDonateModal() {
    const modal = document.getElementById('donateModal');
    if (!modal) return;

    modal.style.display = 'block';
    // Небольшая задержка для плавной анимации
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

/**
 * Закрыть модалку доната
 */
function closeDonateModal() {
    const modal = document.getElementById('donateModal');
    if (!modal) return;

    modal.classList.remove('show');
    // Скрываем после анимации
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

/**
 * Копировать адрес доната в буфер обмена
 */
function copyDonateAddress() {
    const addressInput = document.getElementById('donateAddress');
    if (!addressInput) return;

    // Выделяем текст
    addressInput.select();
    addressInput.setSelectionRange(0, 99999); // Для мобильных устройств

    // Копируем в буфер обмена
    try {
        navigator.clipboard.writeText(addressInput.value).then(() => {
            toast.success('Адрес скопирован в буфер обмена!');
        }).catch(() => {
            // Fallback для старых браузеров
            document.execCommand('copy');
            toast.success('Адрес скопирован в буфер обмена!');
        });
    } catch (err) {
        console.error('Failed to copy address:', err);
        toast.error('Не удалось скопировать адрес');
    }
}

// Делаем функции глобальными для вызова из HTML
window.openDonateModal = openDonateModal;
window.closeDonateModal = closeDonateModal;
window.copyDonateAddress = copyDonateAddress;

// ========== First Run Modal ========== //

/**
 * Открыть модалку первого запуска
 * Проверяет localStorage - показывает только 1 раз за сессию first_run
 */
function openFirstRunModal() {
    const modal = document.getElementById('firstRunModal');
    if (!modal) return;

    // Проверяем, показывали ли уже модалку в этой сессии
    const modalShown = localStorage.getItem('firstRunModalShown');
    if (modalShown === 'true') {
        console.log('First run modal already shown, skipping');
        return;
    }

    modal.style.display = 'block';
    // Небольшая задержка для плавной анимации
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

/**
 * Закрыть модалку первого запуска
 * Сохраняет флаг в localStorage, чтобы не показывать повторно
 */
function closeFirstRunModal() {
    const modal = document.getElementById('firstRunModal');
    if (!modal) return;

    // Сохраняем флаг, что модалка была показана и закрыта
    localStorage.setItem('firstRunModalShown', 'true');

    modal.classList.remove('show');
    // Скрываем после анимации
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

/**
 * Инициализация обработчиков для модалки первого запуска
 */
function initFirstRunModal() {
    const modal = document.getElementById('firstRunModal');
    if (!modal) return;

    // Закрытие модалки при клике на фон
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeFirstRunModal();
        }
    });

    // Закрытие по Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('show')) {
            closeFirstRunModal();
        }
    });
}

// Делаем функции глобальными
window.openFirstRunModal = openFirstRunModal;
window.closeFirstRunModal = closeFirstRunModal;

// Инициализируем обработчики при загрузке
document.addEventListener('DOMContentLoaded', () => {
    initFirstRunModal();
});

// ========== PWA Service Worker ========== //

/**
 * Проверка доступности PWA (требуется HTTPS или localhost)
 * @returns {boolean} true если PWA может работать
 */
function isPWASupported() {
    const isSecureContext = window.location.protocol === 'https:' ||
                           window.location.hostname === 'localhost' ||
                           window.location.hostname === '127.0.0.1' ||
                           window.location.hostname === '[::1]';

    const hasServiceWorker = 'serviceWorker' in navigator;
    const hasCacheAPI = 'caches' in window;

    return isSecureContext && hasServiceWorker && hasCacheAPI;
}

// Экспортируем для использования в других скриптах
window.isPWASupported = isPWASupported;

/**
 * Регистрация Service Worker для PWA
 * Обеспечивает кеширование статики и работу offline
 * ТРЕБУЕТ: HTTPS или localhost
 */
if (isPWASupported()) {
    window.addEventListener('load', async () => {
        try {
            const registration = await navigator.serviceWorker.register('/static/service-worker.js');
            console.log('[PWA] Service Worker registered:', registration.scope);

            // Проверка обновлений каждые 60 секунд
            setInterval(() => {
                registration.update();
            }, 60000);

            // Обработка обновлений
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;

                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        // Новая версия доступна
                        console.log('[PWA] New version available');

                        // Показываем уведомление пользователю
                        if (window.showToast) {
                            showToast('Доступна новая версия. Перезагрузите страницу для обновления.', 'info', 10000);
                        }
                    }
                });
            });

        } catch (error) {
            console.error('[PWA] Service Worker registration failed:', error);
        }
    });
} else {
    console.log('[PWA] Service Worker not available (requires HTTPS or localhost)');
}

/**
 * Очистка всех кешей браузера
 * Используется из настроек для принудительного обновления
 * ТРЕБУЕТ: HTTPS или localhost
 */
async function clearBrowserCache() {
    if (!isPWASupported()) {
        showToast('PWA недоступен. Требуется HTTPS или localhost.', 'error');
        return false;
    }

    if (!('caches' in window)) {
        showToast('Cache API не поддерживается', 'error');
        return false;
    }

    try {
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames.map(name => caches.delete(name)));

        // Отправляем сообщение service worker
        if (navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_CACHE' });
        }

        console.log('[PWA] Browser cache cleared');
        return true;
    } catch (error) {
        console.error('[PWA] Failed to clear cache:', error);
        return false;
    }
}

// Экспортируем функцию для использования в настройках
window.clearBrowserCache = clearBrowserCache;
