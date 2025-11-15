/**
 * Alerts page functionality
 */

// Global module names cache
let moduleNamesCache = {};
let allModules = [];

document.addEventListener('DOMContentLoaded', async () => {
    // Load module names first and wait for completion
    await loadModuleNames();

    // Load module filter options
    await loadAllModuleOptions();

    // Load alerts on page load (now module names are cached)
    loadAlerts();

    // Handle filter changes
    document.getElementById('alertTypeFilter')?.addEventListener('change', loadAlerts);
    document.getElementById('periodFilter')?.addEventListener('change', loadAlerts);
    document.getElementById('moduleFilter')?.addEventListener('change', loadAlerts);

    // Make stat cards clickable for filtering
    setupStatCardFilters();
});

/**
 * Load module names from API
 */
async function loadModuleNames() {
    try {
        const response = await api.get('/modules');
        if (response.modules) {
            moduleNamesCache = {};
            allModules = response.modules;
            response.modules.forEach(module => {
                moduleNamesCache[module.id] = module.name;
            });
        }
    } catch (error) {
        console.error('Failed to load module names:', error);
    }
}

/**
 * Load all module options for filter (called once on page load)
 */
async function loadAllModuleOptions() {
    const moduleFilter = document.getElementById('moduleFilter');
    if (!moduleFilter || allModules.length === 0) return;

    // Keep current selection
    const currentValue = moduleFilter.value;

    // Build options from all modules
    moduleFilter.innerHTML = '<option value="all">Все модули</option>';
    allModules.forEach(module => {
        const option = document.createElement('option');
        option.value = module.id;
        option.textContent = module.name;
        moduleFilter.appendChild(option);
    });

    // Restore selection if it exists
    if (currentValue && allModules.find(m => m.id === currentValue)) {
        moduleFilter.value = currentValue;
    }
}

/**
 * Load and display alerts
 */
async function loadAlerts() {
    const alertsList = document.getElementById('alertsList');
    const alertTypeFilter = document.getElementById('alertTypeFilter')?.value || 'all';
    const periodFilter = document.getElementById('periodFilter')?.value || '7d';
    const moduleFilter = document.getElementById('moduleFilter')?.value || 'all';

    // Show loading skeleton
    alertsList.innerHTML = `
        <div class="skeleton-line"></div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line"></div>
    `;

    try {
        // Build query params
        let queryParams = `period=${periodFilter}`;
        if (alertTypeFilter !== 'all') {
            queryParams += `&severity=${alertTypeFilter}`;
        }
        if (moduleFilter !== 'all') {
            queryParams += `&module_id=${moduleFilter}`;
        }

        // Fetch alerts from API
        const response = await api.get(`/alerts?${queryParams}`);

        // Update statistics
        updateAlertStats(response);

        // Display alerts (filter out hidden)
        const alerts = response.alerts || [];
        const hiddenAlerts = getHiddenAlerts();
        const visibleAlerts = alerts.filter(alert => !hiddenAlerts.includes(alert.run_id));

        if (visibleAlerts.length === 0) {
            alertsList.innerHTML = `
                <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                    <p>Нет алертов для отображения</p>
                    <p style="font-size: 14px;">Все модули работают нормально</p>
                </div>
            `;
        } else {
            alertsList.innerHTML = visibleAlerts.map(alert => renderAlert(alert)).join('');
        }

    } catch (error) {
        console.error('Failed to load alerts:', error);
        alertsList.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <p>Ошибка загрузки алертов</p>
                <p style="font-size: 14px;">${error.message || 'Попробуйте обновить страницу'}</p>
            </div>
        `;
    }
}

/**
 * Format module ID to readable name
 * @param {string} moduleId
 * @returns {string}
 */
function formatModuleName(moduleId) {
    // Try to get name from cache first (loaded from API)
    if (moduleNamesCache[moduleId]) {
        return moduleNamesCache[moduleId];
    }

    // Fallback: format from ID
    return moduleId
        .replace(/_/g, ' ')
        .replace(/alert/gi, '')
        .trim()
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Update alert statistics
 * @param {object} response - API response with alerts
 */
function updateAlertStats(response) {
    document.getElementById('criticalCount').textContent = response.critical_count || 0;
    document.getElementById('highCount').textContent = response.high_count || 0;
    document.getElementById('mediumCount').textContent = response.medium_count || 0;
}

/**
 * Render single alert
 * @param {object} alert
 * @returns {string}
 */
function renderAlert(alert) {
    const severityClass = alert.severity || 'medium';
    const severityLabel = {
        'critical': 'КРИТИЧНО',
        'high': 'ВАЖНО',
        'medium': 'СРЕДНЕ',
        'low': 'НИЗКО'
    }[severityClass] || severityClass.toUpperCase();

    const time = alert.created_at ? new Date(alert.created_at).toLocaleString('ru-RU') : 'Только что';
    const moduleName = formatModuleName(alert.module_id || 'unknown');
    const moduleUrl = alert.module_id ? `/modules/${alert.module_id}` : '#';

    // Format message - replace \n with <br>
    const formattedMessage = (alert.message || 'Нет описания')
        .replace(/\n/g, '<br>');

    // Format recommended action if exists
    const actionHtml = alert.recommended_action ? `
        <div class="alert-action">
            <strong>Рекомендация:</strong> ${alert.recommended_action}
        </div>
    ` : '';

    return `
        <div class="alert-item ${severityClass}" data-run-id="${alert.run_id}"
             onclick="window.location.href='${moduleUrl}'"
             title="Открыть модуль ${moduleName}">
            <div class="alert-content">
            <div class="alert-header">
                <div class="alert-title">
                    <span class="alert-badge ${severityClass}">${severityLabel}</span>
                </div>
            </div>
            <div class="alert-message">${formattedMessage}</div>
            ${actionHtml}
            <div class="alert-meta">
                <span>Модуль: <strong>${moduleName}</strong></span>
                <span>Время: ${time}</span>
            </div>
            </div>
            <div class="alert-actions" onclick="event.stopPropagation()">
                <button class="btn-action btn-hide" onclick="hideAlert(${alert.run_id})">
                    Скрыть
                </button>
                <button style="background: #c03642; color: #fff;" class="btn-action btn-delete" data-run-id="${alert.run_id}" onclick="deleteAlert(${alert.run_id})">
                    Удалить
                </button>
            </div>
        </div>
    `;
}

/**
 * Delete alert
 * @param {number} runId
 */
async function deleteAlert(runId) {
    const confirmed = await showCustomConfirm({
        title: 'Удалить алерт?',
        message: 'Это удалит алерт и запись из истории модуля.<br><br>Отменить это действие будет невозможно.',
        confirmText: 'Удалить',
        cancelText: 'Отмена',
        storageKey: 'alerts_delete_warning'
    });

    if (!confirmed) return;

    try {
        await api.delete(`/alerts/${runId}`);
        toast.success('Алерт удален');
        // Reload alerts
        loadAlerts();
    } catch (error) {
        console.error('Failed to delete alert:', error);
        toast.error('Ошибка при удалении алерта');
    }
}

/**
 * Delete all alerts
 */
async function deleteAllAlerts() {
    const confirmed = await showCustomConfirm({
        title: 'Удалить все алерты?',
        message: 'Это удалит все алерты и записи из истории модулей для текущих фильтров.<br><br><strong>Отменить это действие будет невозможно!</strong>',
        confirmText: 'Удалить все',
        cancelText: 'Отмена',
        storageKey: 'alerts_delete_all_warning'
    });

    if (!confirmed) return;

    try {
        // Get current filters
        const alertTypeFilter = document.getElementById('alertTypeFilter')?.value || 'all';
        const periodFilter = document.getElementById('periodFilter')?.value || '7d';
        const moduleFilter = document.getElementById('moduleFilter')?.value || 'all';

        // Build query params (same as loadAlerts)
        let queryParams = `period=${periodFilter}`;
        if (alertTypeFilter !== 'all') {
            queryParams += `&severity=${alertTypeFilter}`;
        }
        if (moduleFilter !== 'all') {
            queryParams += `&module_id=${moduleFilter}`;
        }

        // Delete all
        await api.delete(`/alerts/bulk?${queryParams}`);
        toast.success('Все алерты удалены');

        // Reload
        loadAlerts();
    } catch (error) {
        console.error('Failed to delete all alerts:', error);
        toast.error('Ошибка при удалении алертов');
    }
}

/**
 * Mark all alerts as read (placeholder)
 */
async function markAllAsRead() {
    toast.info('Функция "Отметить все как прочитанные" пока не реализована');
}

/**
 * Export alerts (placeholder)
 */
async function exportAlerts() {
    toast.info('Функция экспорта в разработке');
}

/**
 * Setup stat card filtering
 */
function setupStatCardFilters() {
    const statCards = document.querySelectorAll('.alerts-stats .stat-card');

    statCards.forEach(card => {
        card.style.cursor = 'pointer';
        card.addEventListener('click', function() {
            const alertTypeFilter = document.getElementById('alertTypeFilter');
            if (!alertTypeFilter) return;

            // Determine severity based on card class
            let severity = 'all';
            if (this.classList.contains('critical')) {
                severity = 'critical';
            } else if (this.classList.contains('warning')) {
                severity = 'high';
            } else if (this.classList.contains('info')) {
                severity = 'medium';
            }

            // Update filter and reload
            alertTypeFilter.value = severity;

            // Visual feedback - highlight selected card
            statCards.forEach(c => c.style.opacity = '0.6');
            this.style.opacity = '1';

            // Load alerts with new filter
            loadAlerts();
        });
    });
}

/**
 * Get hidden alerts from localStorage
 * @returns {Array} Array of hidden alert run IDs
 */
function getHiddenAlerts() {
    try {
        const hidden = localStorage.getItem('hiddenAlerts');
        return hidden ? JSON.parse(hidden) : [];
    } catch (e) {
        console.error('Error reading hidden alerts:', e);
        return [];
    }
}

/**
 * Hide alert (store in localStorage)
 * @param {number} runId
 */
function hideAlert(runId) {
    try {
        const hidden = getHiddenAlerts();
        if (!hidden.includes(runId)) {
            hidden.push(runId);
            localStorage.setItem('hiddenAlerts', JSON.stringify(hidden));
        }

        // Remove alert from UI with animation
        const alertItem = document.querySelector(`.alert-item[data-run-id="${runId}"]`);
        if (alertItem) {
            alertItem.style.opacity = '0';
            alertItem.style.transform = 'translateX(100%)';
            setTimeout(() => {
                alertItem.remove();

                // Check if no alerts left
                const alertsList = document.getElementById('alertsList');
                if (!alertsList.querySelector('.alert-item')) {
                    alertsList.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: var(--text-secondary);">
                            <p>Нет алертов для отображения</p>
                            <p style="font-size: 14px;">Все модули работают нормально</p>
                        </div>
                    `;
                }
            }, 300);
        }

        toast.success('Алерт скрыт');
    } catch (e) {
        console.error('Error hiding alert:', e);
        toast.error('Ошибка при скрытии алерта');
    }
}

/**
 * Open Telegram settings modal
 */
async function openTelegramSettings() {
    const modal = document.getElementById('telegramSettingsModal');
    if (!modal) return;

    // Load current settings
    try {
        const response = await api.get('/settings/telegram/alerts');
        const settings = response.settings || [];

        // Populate module checkboxes (async)
        await populateTelegramModules(settings);

        // Show modal
        modal.style.display = 'flex';
    } catch (error) {
        console.error('Error loading telegram settings:', error);
        toast.error('Ошибка загрузки настроек');
    }
}

/**
 * Close Telegram settings modal
 */
function closeTelegramSettings() {
    const modal = document.getElementById('telegramSettingsModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Populate telegram modules checkboxes
 * @param {Array} enabledModules - Array of enabled module IDs
 */
async function populateTelegramModules(enabledModules) {
    try {
        // Load all modules from API
        const response = await api.get('/modules');
        if (!response.modules) {
            console.error('No modules returned from API');
            return;
        }

        // Category mapping to tabs
        const categoryMap = {
            'critical_alerts': 'critical',
            'trend_analysis': 'trend',
            'problem_detection': 'problem',
            'opportunities': 'opportunity',
            // Добавляем недостающие категории
            'stability': 'trend',           // Стабильность → Тренды
            'predictive': 'opportunity',     // Прогнозы → Возможности
            'portfolio': 'trend',            // Портфель → Тренды
            'sources_offers': 'problem'      // Источники/офферы → Проблемы
        };

        // Group modules by tab
        const modulesByTab = {
            critical: [],
            trend: [],
            problem: [],
            opportunity: []
        };

        response.modules.forEach(module => {
            const tab = categoryMap[module.category];
            if (tab && modulesByTab[tab]) {
                modulesByTab[tab].push(module);
            }
        });

        const renderModuleCheckbox = (module, enabled) => {
            return `
                <label class="telegram-module-item">
                    <input type="checkbox" value="${module.id}" ${enabled ? 'checked' : ''}>
                    <span>${module.name}</span>
                </label>
            `;
        };

        // Critical modules (по умолчанию все включены)
        const criticalContainer = document.getElementById('criticalModules');
        if (criticalContainer) {
            if (modulesByTab.critical.length > 0) {
                criticalContainer.innerHTML = modulesByTab.critical
                    .map(m => renderModuleCheckbox(m, enabledModules.length === 0 || enabledModules.includes(m.id)))
                    .join('');
            } else {
                criticalContainer.innerHTML = '<p style="color: var(--text-secondary); padding: 20px;">Нет модулей в этой категории</p>';
            }
        }

        // Trend modules
        const trendContainer = document.getElementById('trendModules');
        if (trendContainer) {
            if (modulesByTab.trend.length > 0) {
                trendContainer.innerHTML = modulesByTab.trend
                    .map(m => renderModuleCheckbox(m, enabledModules.includes(m.id)))
                    .join('');
            } else {
                trendContainer.innerHTML = '<p style="color: var(--text-secondary); padding: 20px;">Нет модулей в этой категории</p>';
            }
        }

        // Problem modules
        const problemContainer = document.getElementById('problemModules');
        if (problemContainer) {
            if (modulesByTab.problem.length > 0) {
                problemContainer.innerHTML = modulesByTab.problem
                    .map(m => renderModuleCheckbox(m, enabledModules.includes(m.id)))
                    .join('');
            } else {
                problemContainer.innerHTML = '<p style="color: var(--text-secondary); padding: 20px;">Нет модулей в этой категории</p>';
            }
        }

        // Opportunity modules
        const opportunityContainer = document.getElementById('opportunityModules');
        if (opportunityContainer) {
            if (modulesByTab.opportunity.length > 0) {
                opportunityContainer.innerHTML = modulesByTab.opportunity
                    .map(m => renderModuleCheckbox(m, enabledModules.includes(m.id)))
                    .join('');
            } else {
                opportunityContainer.innerHTML = '<p style="color: var(--text-secondary); padding: 20px;">Нет модулей в этой категории</p>';
            }
        }
    } catch (error) {
        console.error('Error populating telegram modules:', error);
        toast.error('Ошибка загрузки модулей');
    }
}

/**
 * Save Telegram settings
 */
async function saveTelegramSettings() {
    try {
        // Collect enabled modules
        const modal = document.getElementById('telegramSettingsModal');
        const checkboxes = modal.querySelectorAll('input[type="checkbox"]:checked');
        const enabledModules = Array.from(checkboxes).map(cb => cb.value);

        // Save to backend
        await api.post('/settings/telegram/alerts', {
            enabled_modules: enabledModules
        });

        toast.success('Настройки сохранены');
        closeTelegramSettings();
    } catch (error) {
        console.error('Error saving telegram settings:', error);
        toast.error('Ошибка сохранения настроек');
    }
}

/**
 * Switch between telegram settings tabs
 * @param {string} tabName - Tab name (critical, trend, problem, opportunity)
 */
function switchTelegramTab(tabName) {
    // Hide all tabs and contents
    document.querySelectorAll('.telegram-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.telegram-tab-content').forEach(content => {
        content.classList.remove('active');
    });

    // Show selected tab
    const tabs = document.querySelectorAll('.telegram-tab');
    const tabIndex = {
        'critical': 0,
        'trend': 1,
        'problem': 2,
        'opportunity': 3
    }[tabName] || 0;

    if (tabs[tabIndex]) {
        tabs[tabIndex].classList.add('active');
    }

    // Show selected content
    const contentId = {
        'critical': 'criticalModules',
        'trend': 'trendModules',
        'problem': 'problemModules',
        'opportunity': 'opportunityModules'
    }[tabName];

    const content = document.getElementById(contentId);
    if (content) {
        content.classList.add('active');
    }
}
