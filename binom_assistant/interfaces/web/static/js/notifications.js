/**
 * Модуль управления уведомлениями
 */

let notificationsDropdown = null;
let notificationsList = null;
let notificationBadge = null;
let moduleNamesMap = {}; // Маппинг module_id -> красивое название

// Ключ для localStorage
const READ_ALERTS_KEY = 'binom_read_alerts';

/**
 * Получить список прочитанных алертов из localStorage
 * @returns {Array} Массив run_id прочитанных алертов
 */
function getReadAlerts() {
    try {
        const data = localStorage.getItem(READ_ALERTS_KEY);
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error reading from localStorage:', e);
        return [];
    }
}

/**
 * Сохранить список прочитанных алертов в localStorage
 * @param {Array} runIds - Массив run_id
 */
function saveReadAlerts(runIds) {
    try {
        localStorage.setItem(READ_ALERTS_KEY, JSON.stringify(runIds));
    } catch (e) {
        console.error('Error saving to localStorage:', e);
    }
}

/**
 * Отметить один алерт как прочитанный
 * @param {number} runId - ID запуска модуля
 */
function markAlertAsRead(runId) {
    const readAlerts = getReadAlerts();
    if (!readAlerts.includes(runId)) {
        readAlerts.push(runId);
        saveReadAlerts(readAlerts);
    }
}

/**
 * Отметить несколько алертов как прочитанные
 * @param {Array} runIds - Массив run_id
 */
function markAlertsAsRead(runIds) {
    const readAlerts = getReadAlerts();
    const updated = [...new Set([...readAlerts, ...runIds])]; // Убираем дубликаты
    saveReadAlerts(updated);
}

/**
 * Загрузить маппинг ID модулей -> названия
 */
async function loadModuleNames() {
    try {
        const data = await api.get('/modules');
        const modules = data.modules || [];

        // Создаем маппинг
        moduleNamesMap = {};
        modules.forEach(module => {
            if (module.id && module.name) {
                moduleNamesMap[module.id] = module.name;
            }
        });

        console.log('Loaded module names:', Object.keys(moduleNamesMap).length);
    } catch (error) {
        console.error('Error loading module names:', error);
    }
}

/**
 * Инициализация модуля уведомлений
 */
function initNotifications() {
    const notificationsBtn = document.getElementById('notificationsBtn');
    notificationsDropdown = document.getElementById('notificationsDropdown');
    notificationsList = document.getElementById('notificationsList');
    notificationBadge = document.getElementById('notificationBadge');

    if (!notificationsBtn || !notificationsDropdown) {
        return;
    }

    // Загружаем список модулей для маппинга названий
    loadModuleNames();

    // Клик по кнопке - показать/скрыть
    notificationsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleNotificationsDropdown();
    });

    // Клик вне меню - закрыть
    document.addEventListener('click', (e) => {
        if (notificationsDropdown &&
            notificationsDropdown.style.display === 'flex' &&
            !notificationsDropdown.contains(e.target) &&
            !notificationsBtn.contains(e.target)) {
            closeNotificationsDropdown();
        }
    });

    // Загружаем счетчик при инициализации
    updateNotificationBadge();

    // Автообновление каждые 5 минут
    setInterval(() => {
        updateNotificationBadge();
    }, 300000); // 5 минут
}

/**
 * Показать/скрыть dropdown
 */
function toggleNotificationsDropdown() {
    if (notificationsDropdown.style.display === 'flex') {
        closeNotificationsDropdown();
    } else {
        openNotificationsDropdown();
    }
}

/**
 * Открыть dropdown
 */
async function openNotificationsDropdown() {
    notificationsDropdown.style.display = 'flex';

    // Загружаем уведомления
    await loadNotifications();
}

/**
 * Закрыть dropdown
 */
function closeNotificationsDropdown() {
    notificationsDropdown.style.display = 'none';
}

/**
 * Обновить badge с количеством
 */
async function updateNotificationBadge() {
    try {
        // Получаем все recent алерты (с большим лимитом чтобы охватить все за день)
        const data = await api.get('/alerts/recent?limit=100');
        const alerts = data.alerts || [];

        // Фильтруем прочитанные
        const readAlerts = getReadAlerts();
        const unreadAlerts = alerts.filter(alert => !readAlerts.includes(alert.run_id));

        const count = unreadAlerts.length;

        if (notificationBadge) {
            notificationBadge.textContent = count;
            notificationBadge.setAttribute('data-count', count);

            if (count > 0) {
                notificationBadge.style.display = 'block';
            } else {
                notificationBadge.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error updating notification badge:', error);
    }
}

/**
 * Загрузить список уведомлений
 */
async function loadNotifications() {
    if (!notificationsList) return;

    notificationsList.innerHTML = '<div class="notifications-loading">Загрузка...</div>';

    try {
        const data = await api.get('/alerts/recent?limit=10');
        const alerts = data.alerts || [];

        // Фильтруем прочитанные
        const readAlerts = getReadAlerts();
        const unreadAlerts = alerts.filter(alert => !readAlerts.includes(alert.run_id));

        if (unreadAlerts.length === 0) {
            notificationsList.innerHTML = '<div class="notifications-empty">Нет новых уведомлений</div>';
            return;
        }

        renderNotifications(unreadAlerts);
    } catch (error) {
        console.error('Error loading notifications:', error);
        notificationsList.innerHTML = '<div class="notifications-empty">Ошибка загрузки уведомлений</div>';
    }
}

/**
 * Отрисовать уведомления
 */
function renderNotifications(alerts) {
    const severityIcons = {
        'critical': '/static/icons/critical-ef4444.png',
        'high': '/static/icons/warning-f59e0b.png',
        'medium': '/static/icons/info-A0AFFF.png',
        'warning': '/static/icons/warning-f59e0b.png',
        'info': '/static/icons/info-A0AFFF.png'
    };

    const html = alerts.map(alert => {
        const icon = severityIcons[alert.severity] || severityIcons.info;
        const time = formatNotificationTime(alert.created_at);
        const moduleId = alert.module_id || '';
        const runId = alert.run_id || '';

        // Получаем красивое название модуля из маппинга
        const moduleName = moduleNamesMap[moduleId] ||
                          moduleId.replace(/_/g, ' ').replace(/alert/gi, '').trim() ||
                          'Module';

        return `
            <div class="notification-item unread"
                 data-module-id="${moduleId}"
                 data-run-id="${runId}">
                <div class="notification-icon ${alert.severity}">
                    <img src="${icon}" alt="${alert.severity}">
                </div>
                <div class="notification-content">
                    <div class="notification-title">${moduleName}</div>
                    <div class="notification-message">${alert.message}</div>
                    <div class="notification-time">${time}</div>
                </div>
            </div>
        `;
    }).join('');

    notificationsList.innerHTML = html;

    // Добавляем клик на каждое уведомление
    notificationsList.querySelectorAll('.notification-item').forEach(item => {
        item.addEventListener('click', () => {
            const moduleId = item.getAttribute('data-module-id');
            const runId = parseInt(item.getAttribute('data-run-id'));

            // Отмечаем как прочитанное
            if (runId) {
                markAlertAsRead(runId);
                // Обновляем badge
                updateNotificationBadge();
            }

            // Переход на страницу
            if (moduleId === 'system_logs') {
                // Для system_logs переходим в настройки (раздел логов)
                window.location.href = '/settings';
            } else if (moduleId) {
                // Для модулей переходим на страницу модуля
                window.location.href = `/modules/${moduleId}`;
            } else {
                // Если нет module_id - переходим на общую страницу алертов
                window.location.href = '/alerts';
            }
        });
    });
}

/**
 * Форматировать время для уведомления
 */
function formatNotificationTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 1000 / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Только что';
    if (diffMins < 60) return `${diffMins} мин. назад`;
    if (diffHours < 24) return `${diffHours} ч. назад`;
    if (diffDays < 7) return `${diffDays} д. назад`;

    return date.toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'short'
    });
}

/**
 * Отметить все уведомления как прочитанные
 */
async function markAllAsRead() {
    try {
        // ИСПРАВЛЕНИЕ: Загружаем ВСЕ непрочитанные алерты (не только те что в списке)
        const data = await api.get('/alerts/recent?limit=100');
        const allAlerts = data.alerts || [];

        // Фильтруем прочитанные
        const readAlerts = getReadAlerts();
        const unreadAlerts = allAlerts.filter(alert => !readAlerts.includes(alert.run_id));

        // Собираем все run_id из ВСЕХ непрочитанных алертов
        const runIds = unreadAlerts.map(alert => alert.run_id).filter(id => id);

        if (runIds.length > 0) {
            // Сохраняем в localStorage
            markAlertsAsRead(runIds);

            // Очищаем список уведомлений
            notificationsList.innerHTML = '<div class="notifications-empty">Нет новых уведомлений</div>';

            // Обновляем badge (теперь должен показать 0)
            await updateNotificationBadge();
        }

        closeNotificationsDropdown();
        toast.success('Все уведомления отмечены как прочитанные');

    } catch (error) {
        console.error('Error marking all as read:', error);
        toast.error('Ошибка при отметке уведомлений');
    }
}

/**
 * Показать кастомный confirm dialog
 * @param {object} options - Опции диалога
 * @param {string} options.title - Заголовок
 * @param {string} options.message - Сообщение
 * @param {string} options.confirmText - Текст кнопки подтверждения
 * @param {string} options.cancelText - Текст кнопки отмены
 * @param {string} options.storageKey - Ключ для localStorage (если нужно показывать только раз)
 * @returns {Promise<boolean>} - true если подтвердили, false если отменили
 */
function showCustomConfirm(options) {
    const {
        title = 'Подтверждение',
        message = 'Вы уверены?',
        confirmText = 'Да',
        cancelText = 'Отмена',
        storageKey = null
    } = options;

    return new Promise((resolve) => {
        // Проверяем localStorage - если уже подтверждали, не показываем
        if (storageKey && localStorage.getItem(storageKey) === 'confirmed') {
            resolve(true);
            return;
        }

        // Создаем overlay
        const overlay = document.createElement('div');
        overlay.className = 'custom-confirm-overlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
            animation: fadeIn 0.2s;
        `;

        // Создаем диалог
        const dialog = document.createElement('div');
        dialog.className = 'custom-confirm-dialog';
        dialog.style.cssText = `
            background: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            max-width: 400px;
            width: 90%;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            animation: slideIn 0.2s;
        `;

        // Заголовок
        const titleEl = document.createElement('h3');
        titleEl.textContent = title;
        titleEl.style.cssText = `
            margin: 0 0 12px 0;
            color: var(--text-primary);
            font-size: 18px;
        `;

        // Сообщение
        const messageEl = document.createElement('p');
        messageEl.innerHTML = message;
        messageEl.style.cssText = `
            margin: 0 0 20px 0;
            color: var(--text-secondary);
            font-size: 14px;
            line-height: 1.5;
        `;

        // Чекбокс "Не показывать снова" (если есть storageKey)
        let dontShowAgainCheckbox = null;
        if (storageKey) {
            const checkboxWrapper = document.createElement('div');
            checkboxWrapper.style.cssText = `
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 8px;
            `;

            dontShowAgainCheckbox = document.createElement('input');
            dontShowAgainCheckbox.type = 'checkbox';
            dontShowAgainCheckbox.id = 'dontShowAgain';
            dontShowAgainCheckbox.style.cssText = `
                width: 16px;
                height: 16px;
                cursor: pointer;
            `;

            const label = document.createElement('label');
            label.htmlFor = 'dontShowAgain';
            label.textContent = 'Больше не показывать это предупреждение';
            label.style.cssText = `
                color: var(--text-secondary);
                font-size: 13px;
                cursor: pointer;
            `;

            checkboxWrapper.appendChild(dontShowAgainCheckbox);
            checkboxWrapper.appendChild(label);
            dialog.appendChild(titleEl);
            dialog.appendChild(messageEl);
            dialog.appendChild(checkboxWrapper);
        } else {
            dialog.appendChild(titleEl);
            dialog.appendChild(messageEl);
        }

        // Кнопки
        const buttonsWrapper = document.createElement('div');
        buttonsWrapper.style.cssText = `
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        `;

        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = cancelText;
        cancelBtn.className = 'btn-secondary';
        cancelBtn.style.cssText = `
            padding: 8px 16px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background: transparent;
            color: var(--text-primary);
            cursor: pointer;
            font-size: 14px;
        `;
        cancelBtn.onmouseover = () => cancelBtn.style.background = 'rgba(255,255,255,0.05)';
        cancelBtn.onmouseout = () => cancelBtn.style.background = 'transparent';

        const confirmBtn = document.createElement('button');
        confirmBtn.textContent = confirmText;
        confirmBtn.className = 'btn-danger';
        confirmBtn.style.cssText = `
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            background: #dc3545;
            color: white;
            cursor: pointer;
            font-size: 14px;
        `;
        confirmBtn.onmouseover = () => confirmBtn.style.background = '#c82333';
        confirmBtn.onmouseout = () => confirmBtn.style.background = '#dc3545';

        buttonsWrapper.appendChild(cancelBtn);
        buttonsWrapper.appendChild(confirmBtn);
        dialog.appendChild(buttonsWrapper);

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        // Управление фокусом - захват фокуса внутри диалога
        const focusableElements = dialog.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        // Устанавливаем фокус на первый элемент
        if (firstElement) {
            firstElement.focus();
        }

        // Ловушка для Tab - удерживаем фокус внутри диалога
        const trapFocus = (e) => {
            if (e.key === 'Tab') {
                if (e.shiftKey) {
                    // Shift + Tab
                    if (document.activeElement === firstElement) {
                        e.preventDefault();
                        lastElement.focus();
                    }
                } else {
                    // Tab
                    if (document.activeElement === lastElement) {
                        e.preventDefault();
                        firstElement.focus();
                    }
                }
            }
        };

        dialog.addEventListener('keydown', trapFocus);

        // Обработчики
        const cleanup = () => {
            dialog.removeEventListener('keydown', trapFocus);
            overlay.style.animation = 'fadeOut 0.2s';
            setTimeout(() => overlay.remove(), 200);
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        confirmBtn.onclick = () => {
            // Сохраняем в localStorage если нужно
            if (storageKey && dontShowAgainCheckbox && dontShowAgainCheckbox.checked) {
                localStorage.setItem(storageKey, 'confirmed');
            }
            cleanup();
            resolve(true);
        };

        // Закрытие по клику вне диалога
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                cleanup();
                resolve(false);
            }
        };

        // Закрытие по Escape
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                cleanup();
                resolve(false);
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);
    });
}

// Экспортируем для использования в main.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { initNotifications, updateNotificationBadge, markAllAsRead, showCustomConfirm };
}
