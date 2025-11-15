/**
 * Страница детального просмотра модуля
 */

// ============================================
// МОДУЛЬНАЯ СИСТЕМА
// ============================================

/**
 * Получение модуля из реестра
 * @param {string} moduleId - ID модуля
 * @returns {Object|null}
 */
function getModule(moduleId) {
    if (typeof ModuleRegistry !== 'undefined') {
        return ModuleRegistry.get(moduleId);
    }
    return null;
}

// ============================================
// СОСТОЯНИЕ И ИНИЦИАЛИЗАЦИЯ
// ============================================

// Состояние
const state = {
    moduleId: null,
    moduleData: null,
    currentTab: 'results',
    pollInterval: null,
    hasUnsavedChanges: false,
    // Для сортировки таблицы
    campaigns: [],
    sortColumn: null,
    sortDirection: 'asc'
};

// Извлекаем ID модуля из URL
function getModuleIdFromUrl() {
    const path = window.location.pathname;
    const match = path.match(/\/modules\/([^\/]+)/);
    return match ? match[1] : null;
}

/**
 * Инициализация страницы
 */
document.addEventListener('DOMContentLoaded', async () => {
    state.moduleId = getModuleIdFromUrl();

    if (!state.moduleId) {
        showError('Не указан ID модуля');
        return;
    }

    // Загружаем конфигурацию приложения (BINOM_URL и др.)
    await loadAppConfig();

    // Загружаем данные модуля
    await loadModuleData();

    // Настраиваем вкладки
    setupTabs();

    // Настраиваем кнопки
    setupButtons();

    // Проверяем hash в URL для переключения вкладки
    checkUrlHash();

    // Скрываем loader
    hideLoader();
});

/**
 * Загрузка данных модуля
 */
async function loadModuleData() {
    try {
        // Получаем информацию о модуле
        const moduleInfo = await api.get(`/modules/${state.moduleId}`);
        state.moduleData = moduleInfo;

        // Обновляем заголовок страницы
        updatePageHeader(moduleInfo);

        // Заполняем настройки
        populateSettings(moduleInfo);

        // Заполняем вкладку "О модуле"
        populateAboutTab(moduleInfo);

        // Загружаем результаты последнего запуска
        // Загружаем если есть last_result ИЛИ если запрошена вкладка results
        const hash = window.location.hash.substring(1);
        if (moduleInfo.last_result || moduleInfo.status === 'completed' || moduleInfo.status === 'running' || hash === 'results') {
            await loadResults();
        }

        // Загружаем историю
        const history = await loadHistory();

        // Автозагрузка последнего результата из истории, если результаты еще не загружены
        const hasResults = moduleInfo.last_result || moduleInfo.status === 'completed' || moduleInfo.status === 'running';
        if (!hasResults && history && history.runs && history.runs.length > 0) {
            // Берем самую свежую запись (первая в списке)
            const latestRun = history.runs[0];
            if (latestRun.status === 'success') {
                console.log('Автозагрузка последнего результата из истории:', latestRun.id);
                await viewHistoryRun(latestRun.id, true); // silent=true для автозагрузки
            }
        }

        // Если модуль выполняется, начинаем polling
        if (moduleInfo.status === 'running') {
            startPolling();
        }
    } catch (error) {
        console.error('Ошибка загрузки данных модуля:', error);
        showError('Не удалось загрузить данные модуля');
    }
}

/**
 * Обновление заголовка страницы
 */
function updatePageHeader(moduleInfo) {
    // Обновляем заголовок и описание
    const titleElement = document.getElementById('moduleTitle');
    const descElement = document.getElementById('moduleDescription');

    const name = moduleInfo.metadata?.name || moduleInfo.name || 'Module';
    const description = moduleInfo.metadata?.description || moduleInfo.description || '';

    if (titleElement) titleElement.textContent = name;
    if (descElement) descElement.textContent = description;

    // Статус показываем на основе наличия schedule (автозапуск)
    const statusBadge = document.getElementById('moduleStatus');
    if (statusBadge) {
        const schedule = moduleInfo.config && moduleInfo.config.schedule;
        const isEnabled = !!(schedule && schedule.trim());
        statusBadge.textContent = isEnabled ? 'Включен' : 'Выключен';
        statusBadge.className = `module-status-badge status-${isEnabled ? 'enabled' : 'disabled'}`;
    }

    // Обновляем title страницы
    document.title = `${name} - Binom Assistant`;
}

/**
 * Загрузка результатов
 */
async function loadResults() {
    try {
        const results = await api.get(`/modules/${state.moduleId}/results`);

        // Сохраняем результаты для экспорта
        state.lastResults = results;

        // Отображаем сводку
        renderSummary(results);

        // Отображаем таблицу
        renderResultsTable(results);

        // Отображаем графики
        renderCharts(results);

        // Отображаем алерты
        renderAlerts(results);
    } catch (error) {
        console.error('Ошибка загрузки результатов:', error);

        // Если 404 - значит результатов еще нет
        if (error.message && error.message.includes('404')) {
            document.getElementById('summaryGrid').innerHTML = '<p class="text-muted">Результаты еще не были получены. Запустите модуль чтобы увидеть результаты.</p>';
            document.getElementById('resultsTable').innerHTML = '';
            document.getElementById('chartsContainer').innerHTML = '';
            document.getElementById('alertsContainer').innerHTML = '';
        } else {
            // Другая ошибка - показываем сообщение
            document.getElementById('summaryGrid').innerHTML = `<p class="text-danger">Ошибка загрузки результатов: ${error.message}</p>`;
        }
    }
}

/**
 * Отрисовка параметров запуска
 */
function renderRunParams(results) {
    const params = results.params || (results.data && results.data.params);
    if (!params) {
        return '';
    }

    const paramMetadata = (state.moduleData && state.moduleData.param_metadata) || {};
    const severityMetadata = (state.moduleData && state.moduleData.severity_metadata) || {};
    const module = getModule(state.moduleId);
    const paramParts = [];

    // Получаем список severity параметров для исключения
    const severityKeys = severityMetadata.thresholds ? Object.keys(severityMetadata.thresholds) : [];

    Object.entries(params).forEach(([key, value]) => {
        // Пропускаем severity параметры - они техничные, не нужны в отображении
        if (severityKeys.includes(key)) {
            return;
        }

        let metadata = paramMetadata[key];
        let label = key;
        let formattedValue = value;

        // 1. Сначала ищем в метаданных модуля (из API)
        if (metadata && metadata.label) {
            label = metadata.label;
        }
        // 2. Затем в модульных переводах
        else if (module && module.paramTranslations && module.paramTranslations[key]) {
            label = module.paramTranslations[key];
        }
        // 3. Fallback на общие переводы
        else {
            const commonParamLabels = {
                min_leads: 'Минимум лидов',
                min_spend: 'Минимальный расход',
                days: 'Период анализа',
                roi_threshold: 'Порог ROI',
                min_cost: 'Минимальный расход',
                severity_critical: 'Критичный порог',
                severity_high: 'Высокий порог',
                severity_medium: 'Средний порог',
                severity_low: 'Низкий порог'
            };
            label = commonParamLabels[key] || key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
        }

        // Форматируем значение в зависимости от ключа
        if (key.startsWith('severity_')) {
            // Для severity параметров используем метаданные для определения единицы измерения
            const unit = severityMetadata.metric_unit || '';
            formattedValue = unit ? `${value}${unit}` : value;
        } else if (key === 'roi_threshold') {
            formattedValue = `${value}%`;
        } else if (key === 'cr_drop_threshold' || key === 'cr_growth_threshold') {
            formattedValue = `${value}%`;
        } else if (key === 'traffic_stability') {
            formattedValue = `±${value}%`;
        } else if (key === 'sigma_threshold') {
            formattedValue = `${value}σ`;
        } else if (key === 'significant_change') {
            formattedValue = `${value}%`;
        } else if (key === 'spike_threshold' || key === 'min_spend' || key === 'min_base_spend' || key.includes('spend') || key.includes('cost')) {
            formattedValue = `$${value}`;
        } else if (key === 'base_days' || key === 'days' || key === 'consecutive_days' || key === 'analysis_period' || key.includes('period')) {
            formattedValue = `${value} дней`;
        } else if (key === 'sigma_multiplier') {
            formattedValue = `${value}x`;
        } else if (key.includes('percent') || key.includes('rate') || key.includes('growth')) {
            formattedValue = `${value}%`;
        } else if (key === 'min_leads' || key === 'min_clicks') {
            formattedValue = `${value}`;
        }

        paramParts.push(`${label}: ${formattedValue}`);
    });

    if (paramParts.length === 0) {
        return ''; // Нет распознанных параметров
    }

    // Форматируем время запуска, если оно есть
    let startedAtHtml = '';
    if (results.started_at) {
        startedAtHtml = `
            <div style="color: var(--text-primary); font-size: 13px;">
                <strong style="color: var(--text-primary);">Время запуска:</strong> ${formatDate(results.started_at)}
            </div>
        `;
    }

    return `
        <div class="run-params" style="display: flex; gap: 1rem;background: var(--card-bg); padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; border-left: 3px solid var(--primary-color);">
            ${startedAtHtml}
            <div style="color: var(--text-secondary); font-size: 13px;">
                <strong>Параметры запуска:</strong> ${paramParts.join(' | ')}
            </div>
        </div>
    `;
}

/**
 * Отрисовка сводки результатов
 */
function renderSummary(results) {
    const container = document.getElementById('resultsSummary');

    if (!results.data || !results.data.summary) {
        container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
        return;
    }

    const summary = results.data.summary;

    // Добавляем параметры запуска перед summary-grid
    let html = renderRunParams(results);

    html += '<div class="summary-grid">';

    // Поля, которые нужно скрывать когда их значение = 0
    const hiddenIfZero = ['high_count', 'medium_count', 'critical_count'];

    for (const [key, value] of Object.entries(summary)) {
        // Пропускаем поля со значением 0 если они в списке hiddenIfZero
        if (hiddenIfZero.includes(key) && (value === 0 || value === '0')) {
            continue;
        }

        html += `
            <div class="summary-card">
                <div class="summary-label">${formatMetricLabel(key)}</div>
                <div class="summary-value">${formatMetricValue(key, value)}</div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
}

/**
 * Отрисовка таблицы результатов
 */
function renderResultsTable(results) {
    const container = document.getElementById('resultsTable');
    const moduleId = results.module_id;

    // Получаем модуль из реестра
    const module = getModule(moduleId);

    // Все модули должны иметь renderTable функцию
    if (module && module.renderTable && typeof module.renderTable === 'function') {
        module.renderTable(results, container);
        return;
    }

    // Если модуль не найден или не имеет renderTable - ошибка
    container.innerHTML = `<p class="text-danger">Ошибка: модуль "${moduleId}" не найден или не имеет функции renderTable</p>`;
    console.error(`Module "${moduleId}" not found or missing renderTable function`);
}

/**
 * Старые функции renderStandardTable удалены - теперь каждый модуль имеет свой renderTable
 */




/**
 * Отрисовка графиков
 */
function renderCharts(results) {
    const container = document.getElementById('chartsContainer');

    if (!results.charts || results.charts.length === 0) {
        container.innerHTML = '<p class="text-muted">Нет графиков для отображения</p>';
        return;
    }

    let html = '';
    results.charts.forEach(chart => {
        // Получаем заголовок из правильного места в структуре
        const chartTitle = chart.options?.plugins?.title?.text || chart.title || 'График';

        html += `
            <div class="chart-card">
                <h3>${chartTitle}</h3>
                <div class="chart-container">
                    <canvas id="chart-${chart.id}"></canvas>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;

    // Рендерим графики через Chart.js
    results.charts.forEach(chart => {
        renderChart(chart);
    });
}

/**
 * Отрисовка одного графика
 */
function renderChart(chartConfig) {
    const canvas = document.getElementById(`chart-${chartConfig.id}`);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Объединяем опции по умолчанию с опциями из конфигурации
    const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    color: '#B0B0B0'
                }
            },
            title: {
                display: false  // Заголовок показываем в HTML, не в Chart.js
            }
        },
        scales: chartConfig.type !== 'pie' && chartConfig.type !== 'doughnut' ? {
            x: {
                ticks: { color: '#B0B0B0' },
                grid: { color: '#3A3A3A' }
            },
            y: {
                ticks: { color: '#B0B0B0' },
                grid: { color: '#3A3A3A' }
            }
        } : {}
    };

    // Объединяем с опциями из chartConfig
    const options = {
        ...defaultOptions,
        ...chartConfig.options,
        plugins: {
            ...defaultOptions.plugins,
            ...(chartConfig.options?.plugins || {})
        }
    };

    new Chart(ctx, {
        type: chartConfig.type,
        data: chartConfig.data,
        options: options
    });
}

/**
 * Отрисовка алертов
 */
function renderAlerts(results) {
    const container = document.getElementById('alertsContainer');

    if (!results.alerts || results.alerts.length === 0) {
        container.innerHTML = '<p class="text-muted">Нет алертов</p>';
        return;
    }

    // Форматируем время создания алерта
    const alertTime = results.started_at ? formatDate(results.started_at) : 'Неизвестно';

    let html = '<div class="alerts-list">';

    results.alerts.forEach(alert => {
        // Обрабатываем переносы строк в сообщении
        const messageHtml = alert.message.replace(/\n/g, '<br>');

        html += `
            <div class="alert-item ${alert.severity}" style="flex-direction: column; align-items: stretch;">
    <div style="display: flex; justify-content: space-between; align-items: start; gap: 1rem; margin-bottom: 0.5rem;">
        <div class="alert-header">
            <div class="alert-title">
                <span class="alert-badge ${alert.severity}">${alert.severity.toUpperCase()}</span>
            </div>
        </div>
        <div class="alert-time" style="white-space: nowrap; font-size: 0.85em; color: var(--text-secondary);">Создан: ${alertTime}</div>
    </div>
    <div class="alert-message">${messageHtml}</div>
    ${alert.recommended_action ? `<div class="alert-action"><strong>Рекомендация:</strong> ${alert.recommended_action}</div>` : ''}
</div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

/**
 * Загрузка истории запусков
 */
async function loadHistory() {
    try {
        const history = await api.get(`/modules/${state.moduleId}/history`);
        renderHistory(history);
        return history; // Возвращаем историю для использования в других функциях
    } catch (error) {
        console.error('Ошибка загрузки истории:', error);
        return null;
    }
}

/**
 * Отрисовка истории
 */
function renderHistory(history) {
    const container = document.getElementById('historyContainer');

    if (!history.runs || history.runs.length === 0) {
        container.innerHTML = '<p class="text-muted">История запусков пуста</p>';
        return;
    }

    let html = `
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Дата запуска</th>
                        <th>Статус</th>
                        <th>Время выполнения</th>
                        <th>Результат</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
    `;

    history.runs.forEach(run => {
        html += `
            <tr>
                <td>${formatDate(run.started_at)}</td>
                <td><span class="status-badge status-${run.status}">${getStatusLabel(run.status)}</span></td>
                <td>${run.execution_time_ms ? `${run.execution_time_ms} мс` : '-'}</td>
                <td>${run.summary || '-'}</td>
                <td style="display: flex; gap: 0.5rem;">
                    <button class="btn-action btn-view-history" data-run-id="${run.id}">
                        Просмотр
                    </button>
                    <button class="btn-action btn-delete-history" data-run-id="${run.id}" style="background-color: #dc3545;">
                        Удалить
                    </button>
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;

    // Добавляем обработчики событий для кнопок
    container.querySelectorAll('.btn-view-history').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const runId = e.target.dataset.runId;
            await viewHistoryRun(runId);
        });
    });

    container.querySelectorAll('.btn-delete-history').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const runId = e.target.dataset.runId;
            await deleteHistoryRun(runId);
        });
    });
}

/**
 * Настройка вкладок
 */
function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;

            // Убираем активный класс со всех вкладок
            tabButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Добавляем активный класс к выбранной вкладке
            btn.classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');

            // Обновляем состояние
            state.currentTab = tabName;

            // Обновляем hash в URL
            window.location.hash = tabName;
        });
    });
}

/**
 * Настройка кнопок
 */
function setupButtons() {
    // Кнопка "Запустить"
    document.getElementById('runModuleBtn').addEventListener('click', async () => {
        await runModule();
    });

    // Кнопка "Очистить кэш"
    document.getElementById('clearCacheBtn').addEventListener('click', async () => {
        await clearCache();
    });

    // Кнопка "Экспорт"
    const exportBtn = document.getElementById('exportBtn');
    const exportMenu = document.getElementById('exportMenu');

    exportBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportMenu.classList.toggle('show');
    });

    // Закрываем меню при клике вне его
    document.addEventListener('click', () => {
        exportMenu.classList.remove('show');
    });

    // Обработчики экспорта
    document.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
            const format = item.dataset.format;
            exportData(format);
        });
    });

    // Кнопка "Сохранить и запустить"
    const saveAndRunBtn = document.getElementById('saveAndRunBtn');
    if (saveAndRunBtn) {
        saveAndRunBtn.addEventListener('click', async () => {
            await saveAndRun();
        });
    }

    // Кнопка "Сохранить настройки"
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', async () => {
            await saveSettings();
        });
    }

    // Кнопка "Сбросить по умолчанию"
    const resetSettingsBtn = document.getElementById('resetSettingsBtn');
    if (resetSettingsBtn) {
        resetSettingsBtn.addEventListener('click', async () => {
            await resetToDefaults();
        });
    }

    // Обработчик переключения расписания
    const schedulePreset = document.getElementById('moduleSchedulePreset');
    const scheduleCustom = document.getElementById('moduleSchedule');
    const scheduleHelp = document.querySelector('.setting-help');

    if (schedulePreset && scheduleCustom) {
        schedulePreset.addEventListener('change', (e) => {
            if (e.target.value === 'custom') {
                scheduleCustom.style.display = 'block';
                scheduleHelp.style.display = 'block';
            } else {
                scheduleCustom.style.display = 'none';
                scheduleHelp.style.display = 'none';
            }
            // Показываем кнопку сохранения при изменении расписания
            markSettingsChanged();
        });

        // Также отслеживаем изменения в custom поле
        scheduleCustom.addEventListener('change', markSettingsChanged);
    }

    // Обработчик изменения алертов
    const alertsEnabled = document.getElementById('alertsEnabled');
    if (alertsEnabled) {
        alertsEnabled.addEventListener('change', markSettingsChanged);
    }
}

/**
 * Отмечаем что настройки изменены и нужно сохранить
 */
function markSettingsChanged() {
    const saveBtn = document.getElementById('saveSettingsBtn');
    if (saveBtn && !saveBtn.classList.contains('settings-changed')) {
        saveBtn.classList.add('settings-changed');
        saveBtn.textContent = 'Сохранить изменения';
    }
    // Устанавливаем флаг для проверки при уходе со страницы
    state.hasUnsavedChanges = true;
}

/**
 * Сбрасываем флаг изменений после сохранения
 */
function markSettingsSaved() {
    const saveBtn = document.getElementById('saveSettingsBtn');
    if (saveBtn) {
        saveBtn.classList.remove('settings-changed');
        saveBtn.textContent = 'Сохранить настройки';
    }
    state.hasUnsavedChanges = false;
}

/**
 * Показать loader в секции результатов
 */
function showResultsLoader() {
    const loaderHtml = `
        <div style="display: flex; justify-content: center; align-items: center; padding: 3rem;">
            <div class="loader"></div>
            <span style="margin-left: 1rem; color: var(--text-secondary);">Выполняется анализ...</span>
        </div>
    `;

    // Очищаем все контейнеры результатов и показываем loader
    const resultsSummary = document.getElementById('resultsSummary');
    const resultsTable = document.getElementById('resultsTable');
    const chartsContainer = document.getElementById('chartsContainer');
    const alertsContainer = document.getElementById('alertsContainer');

    if (resultsSummary) resultsSummary.innerHTML = loaderHtml;
    if (resultsTable) resultsTable.innerHTML = '';
    if (chartsContainer) chartsContainer.innerHTML = '';
    if (alertsContainer) alertsContainer.innerHTML = '';
}

/**
 * Запуск модуля
 */
async function runModule() {
    try {
        const btn = document.getElementById('runModuleBtn');
        btn.disabled = true;
        btn.innerHTML = '<div class="loader small"></div> Запуск...';

        // Собираем параметры из формы
        const params = {};
        const paramsContainer = document.getElementById('moduleParams');
        if (paramsContainer) {
            const paramInputs = paramsContainer.querySelectorAll('input[id^="param_"]');
            paramInputs.forEach(input => {
                const key = input.id.replace('param_', '');
                let value = input.value;

                // Преобразуем в число если возможно
                if (!isNaN(value) && value !== '') {
                    value = Number(value);
                }

                params[key] = value;
            });
        }

        const response = await api.post(`/modules/${state.moduleId}/run`, {
            params: Object.keys(params).length > 0 ? params : null,
            use_cache: false  // Всегда выполняем свежий запуск через UI и сохраняем в БД
        });

        if (response.status === 'success') {
            showSuccess('Модуль успешно запущен');
            updateModuleStatus('running');

            // Показываем loader в секции результатов
            showResultsLoader();

            startPolling();

            // Переключаемся на вкладку результатов
            setTimeout(() => {
                const resultsTab = document.querySelector('.tab-btn[data-tab="results"]');
                if (resultsTab) {
                    resultsTab.click();
                }
            }, 500);
        } else {
            showError('Ошибка при запуске модуля');
        }
    } catch (error) {
        console.error('Ошибка запуска модуля:', error);
        showError('Не удалось запустить модуль');
    } finally {
        const btn = document.getElementById('runModuleBtn');
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            Запустить
        `;
    }
}

/**
 * Очистка истории запусков
 */
async function clearCache() {
    if (!confirm('Вы уверены, что хотите очистить всю историю запусков модуля?')) {
        return;
    }

    try {
        await api.delete(`/modules/${state.moduleId}/history`);
        showSuccess('История успешно очищена');
        await loadHistory();
    } catch (error) {
        console.error('Ошибка очистки истории:', error);
        showError('Не удалось очистить историю');
    }
}

/**
 * Экспорт данных
 */
function exportData(format) {
    if (!state.lastResults || !state.lastResults.data || !state.lastResults.data.campaigns) {
        showError('Нет данных для экспорта. Запустите модуль.');
        return;
    }

    const campaigns = state.lastResults.data.campaigns;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const filename = `${state.moduleId}_${timestamp}`;

    if (format === 'csv') {
        exportToCSV(campaigns, filename);
    } else if (format === 'json') {
        exportToJSON(campaigns, filename);
    } else {
        showError('Неподдерживаемый формат экспорта');
    }
}

/**
 * Экспорт в CSV
 */
function exportToCSV(campaigns, filename) {
    const headers = ['ID Binom', 'Название', 'Группа', 'ROI (%)', 'Расход ($)', 'Доход ($)', 'Прибыль ($)', 'Клики', 'Лиды', 'Критичность'];
    const rows = campaigns.map(c => [
        c.binom_id || c.campaign_id,
        `"${c.name}"`,
        `"${c.group || ''}"`,
        c.avg_roi.toFixed(2),
        c.total_cost.toFixed(2),
        c.total_revenue.toFixed(2),
        (c.total_revenue - c.total_cost).toFixed(2),
        c.total_clicks || 0,
        c.total_leads || 0,
        c.severity
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    downloadFile(csv, `${filename}.csv`, 'text/csv;charset=utf-8;');
    showSuccess('Данные экспортированы в CSV');
}

/**
 * Экспорт в JSON
 */
function exportToJSON(campaigns, filename) {
    const json = JSON.stringify({
        module: state.moduleId,
        exported_at: new Date().toISOString(),
        campaigns: campaigns
    }, null, 2);

    downloadFile(json, `${filename}.json`, 'application/json');
    showSuccess('Данные экспортированы в JSON');
}

/**
 * Скачивание файла
 */
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Сохранение настроек
 */
async function saveSettings() {
    try {
        const saveBtn = document.getElementById('saveSettingsBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Сохранение...';

        // Собираем настройки
        const alertsEnabled = document.getElementById('alertsEnabled').checked;
        const schedulePreset = document.getElementById('moduleSchedulePreset').value;
        const scheduleCustom = document.getElementById('moduleSchedule').value;

        // Определяем финальное значение расписания независимо от alertsEnabled
        // schedule управляет АВТОЗАПУСКОМ, alertsEnabled управляет ОТПРАВКОЙ АЛЕРТОВ
        let schedule = null;
        if (schedulePreset === 'custom') {
            schedule = scheduleCustom || null;
        } else if (schedulePreset && schedulePreset !== '') {
            schedule = schedulePreset;
        } else {
            // Пустой select = отключен автозапуск
            schedule = '';
        }

        // Собираем параметры модуля
        const params = {};
        const paramInputs = document.querySelectorAll('[id^="param_"]');
        paramInputs.forEach(input => {
            const paramName = input.id.replace('param_', '');
            const paramValue = input.value;

            // Пытаемся преобразовать в число если это число
            if (!isNaN(paramValue) && paramValue !== '') {
                params[paramName] = parseFloat(paramValue);
            } else {
                params[paramName] = paramValue;
            }
        });

        // Валидация параметров
        const validationErrors = [];

        // ROI threshold - от -100 до 0
        if (params.roi_threshold !== undefined) {
            if (params.roi_threshold > 0 || params.roi_threshold < -100) {
                validationErrors.push('Порог ROI должен быть от -100 до 0');
            }
        }

        // Минимальные расходы - не меньше 0.1$
        if (params.min_spend !== undefined && params.min_spend < 0.1) {
            validationErrors.push('Минимальный расход должен быть не менее 0.1$');
        }
        if (params.min_daily_spend !== undefined && params.min_daily_spend < 0.1) {
            validationErrors.push('Минимальный дневной расход должен быть не менее 0.1$');
        }
        if (params.min_base_spend !== undefined && params.min_base_spend < 0.1) {
            validationErrors.push('Минимальный базовый расход должен быть не менее 0.1$');
        }

        // Периоды в днях - от 1 до 90
        if (params.days !== undefined && (params.days > 90 || params.days < 1)) {
            validationErrors.push('Период анализа должен быть от 1 до 90 дней');
        }
        if (params.base_days !== undefined && (params.base_days > 90 || params.base_days < 1)) {
            validationErrors.push('Базовый период должен быть от 1 до 90 дней');
        }
        if (params.analysis_period !== undefined && (params.analysis_period > 90 || params.analysis_period < 1)) {
            validationErrors.push('Период анализа должен быть от 1 до 90 дней');
        }
        if (params.consecutive_days !== undefined && (params.consecutive_days > 30 || params.consecutive_days < 1)) {
            validationErrors.push('Количество дней подряд должно быть от 1 до 30');
        }

        // Минимальные количества
        if (params.min_leads !== undefined && params.min_leads < 1) {
            validationErrors.push('Минимум лидов должен быть не менее 1');
        }
        if (params.min_clicks !== undefined && params.min_clicks < 1) {
            validationErrors.push('Минимум кликов должен быть не менее 1');
        }

        // Пороги и множители - положительные числа
        if (params.spike_threshold !== undefined && params.spike_threshold < 1) {
            validationErrors.push('Порог всплеска должен быть не менее 1 (1x = без изменений)');
        }
        if (params.sigma_multiplier !== undefined && (params.sigma_multiplier < 0.5 || params.sigma_multiplier > 10)) {
            validationErrors.push('Множитель σ должен быть от 0.5 до 10');
        }
        if (params.sigma_threshold !== undefined && (params.sigma_threshold < 0.5 || params.sigma_threshold > 10)) {
            validationErrors.push('Порог сигмы должен быть от 0.5 до 10');
        }

        // Проценты - от 0 до 100
        if (params.cr_drop_threshold !== undefined && (params.cr_drop_threshold < 0 || params.cr_drop_threshold > 100)) {
            validationErrors.push('Порог падения CR должен быть от 0 до 100%');
        }
        if (params.cr_growth_threshold !== undefined && (params.cr_growth_threshold < 0 || params.cr_growth_threshold > 1000)) {
            validationErrors.push('Порог роста CR должен быть от 0 до 1000%');
        }
        if (params.traffic_stability !== undefined && (params.traffic_stability < 0 || params.traffic_stability > 100)) {
            validationErrors.push('Стабильность трафика должна быть от 0 до 100%');
        }
        if (params.significant_change !== undefined && (params.significant_change < 0 || params.significant_change > 1000)) {
            validationErrors.push('Значительное изменение должно быть от 0 до 1000%');
        }

        // Если есть ошибки валидации - показываем их
        if (validationErrors.length > 0) {
            showError('Ошибки валидации:\n' + validationErrors.join('\n'));
            return;
        }

        // Формируем данные для отправки
        const config = {
            enabled: !!(schedule && schedule.trim()),  // enabled = true если есть schedule
            schedule: schedule,
            alerts_enabled: alertsEnabled,
            params: params
        };

        // Отправляем на сервер
        await api.put(`/modules/${state.moduleId}/config`, config);

        showSuccess('Настройки успешно сохранены');

        // Сбрасываем флаг несохраненных изменений
        markSettingsSaved();

        // Обновляем данные модуля
        await loadModuleData();
    } catch (error) {
        console.error('Ошибка при сохранении настроек:', error);
        showError('Не удалось сохранить настройки: ' + error.message);
    } finally {
        const saveBtn = document.getElementById('saveSettingsBtn');
        saveBtn.disabled = false;
        saveBtn.textContent = 'Сохранить настройки';
    }
}

/**
 * Сохранение настроек и запуск модуля
 */
async function saveAndRun() {
    try {
        const saveAndRunBtn = document.getElementById('saveAndRunBtn');
        saveAndRunBtn.disabled = true;

        // Показываем промежуточное состояние
        saveAndRunBtn.innerHTML = '<div class="loader small"></div> Сохранение...';

        // Собираем настройки (копируем логику из saveSettings)
        const alertsEnabled = document.getElementById('alertsEnabled').checked;
        const schedulePreset = document.getElementById('moduleSchedulePreset').value;
        const scheduleCustom = document.getElementById('moduleSchedule').value;

        // Определяем финальное значение расписания
        let schedule = null;
        if (schedulePreset === 'custom') {
            schedule = scheduleCustom || null;
        } else if (schedulePreset && schedulePreset !== '') {
            schedule = schedulePreset;
        } else {
            schedule = '';
        }

        // Собираем параметры модуля
        const params = {};
        const paramInputs = document.querySelectorAll('[id^="param_"]');
        paramInputs.forEach(input => {
            const paramName = input.id.replace('param_', '');
            const paramValue = input.value;

            // Пытаемся преобразовать в число если это число
            if (!isNaN(paramValue) && paramValue !== '') {
                params[paramName] = parseFloat(paramValue);
            } else {
                params[paramName] = paramValue;
            }
        });

        // Формируем данные для отправки (как в saveSettings)
        const config = {
            enabled: !!(schedule && schedule.trim()),
            schedule: schedule,
            alerts_enabled: alertsEnabled,
            params: params
        };

        // Сохраняем настройки (без проверки result.success)
        await api.put(`/modules/${state.moduleId}/config`, config);

        // Сбрасываем флаг несохраненных изменений
        markSettingsSaved();
        showSuccess('Настройки сохранены');

        // Обновляем состояние кнопки для запуска
        saveAndRunBtn.innerHTML = '<div class="loader small"></div> Запуск...';

        // Теперь запускаем модуль (используем тот же формат что и в runModule)
        const response = await api.post(`/modules/${state.moduleId}/run`, {
            params: Object.keys(params).length > 0 ? params : null,
            use_cache: false
        });

        if (response.status === 'success') {
            showSuccess('Модуль успешно запущен');
            updateModuleStatus('running');

            // Показываем loader в секции результатов
            showResultsLoader();

            startPolling();

            // Переключаемся на вкладку результатов
            setTimeout(() => {
                const resultsTab = document.querySelector('.tab-btn[data-tab="results"]');
                if (resultsTab) {
                    resultsTab.click();
                }
            }, 500);
        } else {
            showError('Ошибка при запуске модуля');
        }

    } catch (error) {
        console.error('Ошибка при сохранении и запуске:', error);
        showError('Не удалось сохранить и запустить модуль: ' + error.message);
    } finally {
        const saveAndRunBtn = document.getElementById('saveAndRunBtn');
        saveAndRunBtn.disabled = false;
        saveAndRunBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            Сохранить и запустить
        `;
    }
}

/**
 * Сброс настроек на дефолтные значения
 */
async function resetToDefaults() {
    if (!confirm('Вы уверены, что хотите сбросить все настройки на значения по умолчанию?')) {
        return;
    }

    try {
        const resetBtn = document.getElementById('resetSettingsBtn');
        resetBtn.disabled = true;
        resetBtn.textContent = 'Сброс...';

        // Получаем дефолтную конфигурацию с сервера
        const defaultConfig = await api.get(`/modules/${state.moduleId}/config/default`);

        // Заполняем alerts_enabled
        const alertsEnabledCheckbox = document.getElementById('alertsEnabled');
        if (alertsEnabledCheckbox) {
            alertsEnabledCheckbox.checked = defaultConfig.alerts_enabled || false;
        }

        // Заполняем schedule
        const schedulePreset = document.getElementById('moduleSchedulePreset');
        const scheduleCustom = document.getElementById('moduleSchedule');

        if (defaultConfig.schedule) {
            // Проверяем есть ли такое значение в preset
            const presetOption = Array.from(schedulePreset.options).find(opt => opt.value === defaultConfig.schedule);
            if (presetOption) {
                schedulePreset.value = defaultConfig.schedule;
                scheduleCustom.style.display = 'none';
                scheduleCustom.value = '';
            } else {
                schedulePreset.value = 'custom';
                scheduleCustom.value = defaultConfig.schedule;
                scheduleCustom.style.display = 'block';
            }
        } else {
            schedulePreset.value = '';
            scheduleCustom.value = '';
            scheduleCustom.style.display = 'none';
        }

        // Заполняем параметры
        if (defaultConfig.params) {
            Object.keys(defaultConfig.params).forEach(paramName => {
                const input = document.getElementById(`param_${paramName}`);
                if (input) {
                    input.value = defaultConfig.params[paramName];
                }
            });
        }

        showSuccess('Настройки сброшены на значения по умолчанию. Нажмите "Сохранить" чтобы применить изменения.');
    } catch (error) {
        console.error('Ошибка при сбросе настроек:', error);
        showError('Не удалось сбросить настройки: ' + error.message);
    } finally {
        const resetBtn = document.getElementById('resetSettingsBtn');
        resetBtn.disabled = false;
        resetBtn.textContent = 'Сбросить по умолчанию';
    }
}

/**
 * Заполнение формы настроек
 */
function populateSettings(moduleInfo) {
    if (!moduleInfo || !moduleInfo.config) return;

    const config = moduleInfo.config;

    // Заполняем чекбокс алертов
    const alertsEnabledCheckbox = document.getElementById('alertsEnabled');
    if (alertsEnabledCheckbox) {
        alertsEnabledCheckbox.checked = config.alerts_enabled || false;
    }

    // Заполняем расписание
    const schedulePreset = document.getElementById('moduleSchedulePreset');
    const scheduleCustom = document.getElementById('moduleSchedule');
    const scheduleHelp = document.querySelector('.setting-help');

    if (schedulePreset && scheduleCustom) {
        const schedule = config.schedule || '';

        // Проверяем, есть ли schedule в списке пресетов
        const presetExists = Array.from(schedulePreset.options).some(
            option => option.value === schedule
        );

        if (presetExists) {
            schedulePreset.value = schedule;
            scheduleCustom.style.display = 'none';
            scheduleHelp.style.display = 'none';
        } else if (schedule) {
            // Если расписание есть, но не в пресетах - это custom
            schedulePreset.value = 'custom';
            scheduleCustom.value = schedule;
            scheduleCustom.style.display = 'block';
            scheduleHelp.style.display = 'block';
        } else {
            // Нет расписания
            schedulePreset.value = '';
            scheduleCustom.style.display = 'none';
            scheduleHelp.style.display = 'none';
        }
    }

    // Заполняем параметры модуля
    const paramsContainer = document.getElementById('moduleParams');
    if (paramsContainer && config.params) {
        paramsContainer.innerHTML = '';

        if (Object.keys(config.params).length === 0) {
            paramsContainer.innerHTML = '<p class="empty-message">У этого модуля нет настраиваемых параметров</p>';
        } else {
            // Используем param_metadata с сервера, если есть, иначе хардкодные значения
            const paramMetadata = moduleInfo.param_metadata || {};

            // Получаем переводы из JS модуля как fallback
            const moduleDefinition = typeof ModuleRegistry !== 'undefined' ? ModuleRegistry.get(moduleInfo.metadata.id) : null;
            const paramTranslations = moduleDefinition?.paramTranslations || {};

            // Общие описания параметров
            const commonDescriptions = {
                roi_threshold: 'ROI ниже которого день считается убыточным',
                min_spend: 'Минимальный расход для включения в анализ',
                min_daily_spend: 'Минимальный средний расход в день',
                days: 'Количество последних дней для анализа',
                analysis_period: 'Период анализа в днях',
                consecutive_days: 'Количество дней подряд с плохим ROI',
                min_leads: 'Минимальное количество лидов для анализа',
                base_days: 'Количество дней для расчета базового уровня',
                spike_threshold: 'Во сколько раз расход должен превысить норму',
                sigma_multiplier: 'Чувствительность детектора: меньше значение (1-2) = больше срабатываний на небольшие отклонения, больше значение (3-5) = только крупные аномалии',
                min_base_spend: 'Минимальный базовый расход для анализа',
                cr_growth_threshold: 'Минимальный рост CR для оправдания всплеска',
                cr_drop_threshold: 'Процент падения CR для срабатывания',
                min_clicks: 'Минимальное количество кликов',
                traffic_stability: 'Допустимое отклонение трафика',
                significant_change: 'Значительное изменение метрики в %'
            };

            // Получаем список severity параметров для исключения
            const severityMetadata = moduleInfo.severity_metadata || {};
            const severityKeys = severityMetadata.thresholds ? Object.keys(severityMetadata.thresholds) : [];

            // Параметры теперь получаются через param_metadata с сервера
            Object.entries(config.params).forEach(([key, value]) => {
                // Пропускаем severity параметры - они будут в отдельном блоке
                if (severityKeys.includes(key)) {
                    return;
                }

                const paramDiv = document.createElement('div');
                paramDiv.className = 'setting-item';

                // Используем метаданные с сервера, если есть, затем переводы из модуля, затем fallback
                const paramInfo = paramMetadata[key] || {
                    label: paramTranslations[key] || key,
                    description: commonDescriptions[key] || '',
                    type: 'number'
                };

                // Формируем атрибуты для input
                let inputAttrs = `type="${paramInfo.type}" id="param_${key}" value="${value}" class="setting-input"`;

                // Добавляем атрибуты min/max/step если они есть
                if (paramInfo.min !== undefined) inputAttrs += ` min="${paramInfo.min}"`;
                if (paramInfo.max !== undefined) inputAttrs += ` max="${paramInfo.max}"`;
                if (paramInfo.step !== undefined) inputAttrs += ` step="${paramInfo.step}"`;

                paramDiv.innerHTML = `
                    <label for="param_${key}">${paramInfo.label}</label>
                    <input ${inputAttrs}>
                    ${paramInfo.description ? `<small>${paramInfo.description}</small>` : ''}
                `;
                paramsContainer.appendChild(paramDiv);
            });
        }
    }

    // Рендерим настройки severity если модуль их поддерживает
    renderSeveritySettings(moduleInfo);
}

/**
 * Рендеринг настроек severity (прямо под параметрами модуля)
 */
function renderSeveritySettings(moduleInfo) {
    const severityMetadata = moduleInfo.severity_metadata;

    if (!severityMetadata || !severityMetadata.enabled) {
        return;
    }

    const paramsContainer = document.getElementById('moduleParams');
    if (!paramsContainer || !paramsContainer.parentElement) {
        return;
    }

    // Создаем новую секцию после "Параметры модуля"
    const settingGroupParent = paramsContainer.parentElement.parentElement;

    // Проверяем, не создана ли уже секция
    let severitySection = document.getElementById('severitySettingsSection');
    if (severitySection) {
        severitySection.remove();
    }

    severitySection = document.createElement('div');
    severitySection.id = 'severitySettingsSection';
    severitySection.className = 'setting-group';

    let html = `
        <h3>Настройки алертов</h3>
        <p class="text-muted" style="margin-bottom: 1rem;">${severityMetadata.description}</p>
        <div class="params-grid">
    `;

    // Добавляем инпуты для порогов
    const config = moduleInfo.config;
    const thresholds = severityMetadata.thresholds;

    Object.entries(thresholds).forEach(([key, meta]) => {
        const currentValue = config.params[key] !== undefined ? config.params[key] : meta.default;

        let inputAttrs = `type="${meta.type}" id="param_${key}" value="${currentValue}" class="setting-input"`;

        if (meta.min !== undefined) inputAttrs += ` min="${meta.min}"`;
        if (meta.max !== undefined) inputAttrs += ` max="${meta.max}"`;
        if (meta.step !== undefined) inputAttrs += ` step="${meta.step}"`;

        html += `
            <div class="setting-item">
                <label for="param_${key}">${meta.label}</label>
                <input ${inputAttrs}>
                ${meta.description ? `<small>${meta.description}</small>` : ''}
            </div>
        `;
    });

    html += `</div>`;

    // Добавляем легенду уровней severity
    if (severityMetadata.levels && severityMetadata.levels.length > 0) {
        html += `
            <div style="margin-top: 1.5rem; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <h4 style="margin-bottom: 0.5rem; font-size: 0.875rem;">Уровни критичности:</h4>
                <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
        `;

        severityMetadata.levels.forEach(level => {
            html += `
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 2px; background: ${level.color};"></span>
                    <span style="font-size: 0.75rem;"><strong>${level.label}</strong>: ${level.condition}</span>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    }

    severitySection.innerHTML = html;

    // Вставляем после секции "Параметры модуля"
    settingGroupParent.insertBefore(severitySection, settingGroupParent.querySelector('.settings-actions'));
}

/**
 * Заполнение вкладки "О модуле"
 */
function populateAboutTab(moduleInfo) {
    if (!moduleInfo || !moduleInfo.metadata) return;

    const metadata = moduleInfo.metadata;
    const moduleId = metadata.id;

    // Описание модуля
    const descriptionEl = document.getElementById('aboutDescription');
    if (descriptionEl) {
        descriptionEl.textContent = metadata.detailed_description || metadata.description || 'Описание отсутствует';
    }

    // Получаем модуль из реестра
    const module = getModule(moduleId);

    // Алгоритм работы
    const algorithmEl = document.getElementById('aboutAlgorithm');
    if (algorithmEl) {
        if (module && module.algorithm) {
            algorithmEl.innerHTML = module.algorithm;
        } else {
            algorithmEl.innerHTML = '<p class="text-muted">Описание алгоритма будет добавлено в следующих версиях</p>';
        }
    }

    // Используемые метрики
    const metricsEl = document.getElementById('aboutMetrics');
    if (metricsEl) {
        if (module && module.metrics) {
            metricsEl.innerHTML = module.metrics;
        } else {
            metricsEl.innerHTML = '<p class="text-muted">Описание метрик будет добавлено в следующих версиях</p>';
        }
    }
}

/**
 * Обновление статуса модуля в UI
 */
function updateModuleStatus(status) {
    const badge = document.getElementById('moduleStatus');
    badge.textContent = getStatusLabel(status);
    badge.className = `module-status-badge status-${status}`;

    if (state.moduleData) {
        state.moduleData.status = status;
    }
}

/**
 * Начать polling для обновления статуса
 */
function startPolling() {
    if (state.pollInterval) return;

    state.pollInterval = setInterval(async () => {
        try {
            const moduleInfo = await api.get(`/modules/${state.moduleId}`);

            if (moduleInfo.status !== 'running') {
                // Модуль завершил работу
                stopPolling();
                updateModuleStatus(moduleInfo.status);

                // Перезагружаем результаты
                await loadResults();

                if (moduleInfo.status === 'completed') {
                    showSuccess('Модуль успешно завершил работу');
                } else if (moduleInfo.status === 'error') {
                    showError('Модуль завершился с ошибкой');
                }
            }
        } catch (error) {
            console.error('Ошибка polling:', error);
        }
    }, 3000); // Проверяем каждые 3 секунды
}

/**
 * Остановить polling
 */
function stopPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

/**
 * Просмотр результатов конкретного запуска
 * @param {string} runId - ID запуска
 * @param {boolean} silent - Не показывать уведомления (для автозагрузки)
 */
async function viewHistoryRun(runId, silent = false) {
    try {
        const run = await api.get(`/modules/${state.moduleId}/history/${runId}`);

        if (run.status === 'success' && run.results) {
            // Загружаем результаты в интерфейс
            const results = run.results;
            // Добавляем params и started_at из run для отображения
            results.params = run.params;
            results.started_at = run.started_at;

            // Отображаем сводку
            renderSummary(results);

            // Отображаем таблицу
            renderResultsTable(results);

            // Отображаем графики
            renderCharts(results);

            // Отображаем алерты
            renderAlerts(results);

            // Переключаемся на вкладку "Результаты анализа"
            document.querySelector('.tab-btn[data-tab="results"]').click();

            if (!silent) {
                showSuccess('Результаты загружены');
            }
        } else {
            if (!silent) {
                showError('Результаты недоступны для этого запуска');
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки результатов запуска:', error);
        if (!silent) {
            showError('Не удалось загрузить результаты: ' + error.message);
        }
    }
}

/**
 * Удаление конкретной записи из истории
 */
async function deleteHistoryRun(runId) {
    if (!confirm('Вы уверены, что хотите удалить эту запись из истории?')) {
        return;
    }

    try {
        await api.delete(`/modules/${state.moduleId}/history/${runId}`);
        showSuccess('Запись успешно удалена');
        await loadHistory();
    } catch (error) {
        console.error('Ошибка удаления записи:', error);
        showError('Не удалось удалить запись: ' + error.message);
    }
}

/**
 * Проверка hash в URL
 */
function checkUrlHash() {
    const hash = window.location.hash.substring(1);
    if (hash) {
        const tabBtn = document.querySelector(`.tab-btn[data-tab="${hash}"]`);
        if (tabBtn) {
            tabBtn.click();
        }
    }
}

/**
 * Получение метки статуса
 */
function getStatusLabel(status) {
    const labels = {
        idle: 'Неактивен',
        running: 'Выполняется',
        completed: 'Завершен',
        error: 'Ошибка'
    };
    return labels[status] || status;
}

/**
 * Получение иконки алерта
 */
function getAlertIcon(severity) {
    const icons = {
        critical: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>`,
        high: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
            <line x1="12" y1="9" x2="12" y2="13"></line>
            <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>`,
        medium: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 16v-4"></path>
            <path d="M12 8h.01"></path>
        </svg>`,
        low: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 8v8"></path>
        </svg>`
    };
    return icons[severity] || icons.medium;
}

/**
 * Форматирование названия метрики с учетом модульных переводов
 */
function formatMetricLabel(key) {
    // Сначала ищем перевод в модуле
    const module = getModule(state.moduleId);
    if (module && module.translations && module.translations[key]) {
        return module.translations[key];
    }

    // Если нет - используем общие переводы
    const commonLabels = {
        total_found: 'Найдено кампаний',
        campaigns_count: 'Кампаний',
        revenue: 'Доход',
        cost: 'Расход',
        roi: 'ROI',
        profit: 'Прибыль',
        total_losses: 'Общие убытки',
        total_wasted: 'Потрачено впустую',
        total_leads: 'Лидов без апрувов',
        total_extra_spend: 'Лишние расходы',
        avg_spike_ratio: 'Средний коэффициент всплеска',
        avg_cr_drop: 'Среднее падение CR',
        avg_bad_streak: 'Средняя длительность слива',
        critical_count: 'Критичных',
        high_count: 'Важных',
        medium_count: 'Средних',
        positive_count: 'Растущих',
        negative_count: 'Падающих'
    };

    return commonLabels[key] || key.replace(/_/g, ' ').charAt(0).toUpperCase() + key.replace(/_/g, ' ').slice(1);
}

/**
 * Форматирование значения метрики
 */
function formatMetricValue(key, value) {
    if (key.includes('loss') || key.includes('revenue') || key.includes('cost') || key.includes('profit') || key.includes('spend') || key.includes('wasted')) {
        return `$${parseFloat(value).toFixed(2)}`;
    }
    if (key === 'roi' || key.includes('roi_change')) {
        return `${parseFloat(value).toFixed(2)}%`;
    }
    if (key === 'avg_spike_ratio') {
        return `${parseFloat(value).toFixed(2)}x`;
    }
    if (key === 'avg_bad_streak') {
        return `${parseFloat(value).toFixed(1)} дней`;
    }
    // Перевод тренда
    if (key === 'trend') {
        const trendLabels = {
            'improving': 'Улучшается',
            'stable': 'Стабилен',
            'declining': 'Ухудшается'
        };
        return trendLabels[value] || value;
    }
    return value;
}

/**
 * Форматирование даты
 */
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Показать toast уведомление
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showSuccess(message) {
    showToast(message, 'success');
}

function showError(message) {
    showToast(message, 'error');
}

function hideLoader() {
    const loader = document.getElementById('initial-loader');
    if (loader) {
        loader.classList.add('hidden');
    }
}

// Очистка и проверка несохраненных изменений при уходе со страницы
window.addEventListener('beforeunload', (e) => {
    stopPolling();

    // Проверяем несохраненные изменения
    if (state.hasUnsavedChanges) {
        const message = 'У вас есть несохраненные изменения. Вы уверены, что хотите покинуть страницу?';
        e.preventDefault();
        e.returnValue = message;
        return message;
    }
});
