/**
 * Логика дашборда
 */

let currentPeriod = '7d';
let currentSortBy = 'roi';
let currentMomentumMetric = 'roi'; // Текущая метрика для Momentum Chart
let currentSparklineMetric = 'clicks'; // Текущая метрика для Sparkline Chart (по умолчанию Клики)
let momentumData = null; // Данные для Momentum Chart
let sparklineData = null; // Данные для Sparkline Chart
let roiChart = null;
let spendChart = null;
let revenueChart = null;
let trendChart = null;
let comparisonChart = null;
let deltaChart = null;
let sparklineChart = null;
let dashboardModuleNames = {}; // Маппинг module_id -> русское название

/**
 * Загрузка статистики
 */
async function loadStats() {
    try {
        const cacheKey = `stats_${currentPeriod}`;
        let data = cache.get(cacheKey);

        if (!data) {
            data = await api.get(`/stats/summary?period=${currentPeriod}`);
            cache.set(cacheKey, data);
        }

        updateStatsCards(data);
        updateLastUpdateTime();
    } catch (error) {
        console.error('Failed to load stats:', error);
        toast.error('Ошибка загрузки статистики');
    }
}

/**
 * Обновление статистических карточек
 */
function updateStatsCards(data) {
    const statsGrid = document.querySelector('.stats-grid');
    if (!statsGrid) return;

    // Проверяем наличие данных
    if (!data) {
        data = {
            total_cost: 0,
            total_revenue: 0,
            total_profit: 0,
            roi: 0,
            campaigns_count: 0
        };
    }

    // Вычисляем profit если не пришел из API
    const profit = data.total_profit !== undefined ? data.total_profit : (data.total_revenue - data.total_cost);

    statsGrid.innerHTML = `
        <div class="stat-card">
            <h3 style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">Общий расход</h3>
            <div style="font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem;">${formatters.currency(data.total_cost || 0)}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">За ${getPeriodLabel(currentPeriod)}</div>
        </div>

        <div class="stat-card">
            <h3 style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">Общий доход</h3>
            <div style="font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem;">${formatters.currency(data.total_revenue || 0)}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">За ${getPeriodLabel(currentPeriod)}</div>
        </div>

        <div class="stat-card">
            <h3 style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">Чистая прибыль</h3>
            <div style="font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem; color: ${profit > 0 ? 'var(--roi-positive)' : 'var(--roi-negative)'}">
                ${formatters.currency(profit || 0)}
            </div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">За ${getPeriodLabel(currentPeriod)}</div>
        </div>

        <div class="stat-card">
            <h3 style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">ROI</h3>
            <div style="font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem; color: ${data.roi > 0 ? 'var(--roi-positive)' : 'var(--roi-negative)'}">
                ${data.roi ? formatters.percent(data.roi) : '0%'}
            </div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">Средний ROI</div>
        </div>

        <div class="stat-card">
            <h3 style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">Кампаний</h3>
            <div style="font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem;">${formatters.number(data.campaigns_count || 0)}</div>
            <div style="font-size: 0.75rem; color: var(--text-secondary);">Активных кампаний</div>
        </div>
    `;
}

/**
 * Получить метку периода
 */
function getPeriodLabel(period) {
    const labels = {
        '1d': 'сегодня',
        'yesterday': 'вчера',
        '7d': 'последние 7 дней',
        '14d': 'последние 14 дней',
        '30d': 'последние 30 дней',
        'this_month': 'этот месяц',
        'last_month': 'прошлый месяц'
    };
    return labels[period] || period;
}

/**
 * Загрузка сводки по источникам, офферам и партнеркам
 */
async function loadSummaryInfo() {
    try {
        const cacheKey = `summary_${currentPeriod}`;
        let data = cache.get(cacheKey);

        if (!data) {
            data = await api.get(`/dashboard/summary?period=${currentPeriod}`);
            cache.set(cacheKey, data);
        }

        updateSummaryInfo(data);
    } catch (error) {
        console.error('Failed to load summary info:', error);
        // Не показываем toast, чтобы не раздражать пользователя
    }
}

/**
 * Обновление блока сводки
 */
function updateSummaryInfo(data) {
    // Топ источник
    const tsTop = document.getElementById('tsTop');
    if (tsTop && data.traffic_sources && data.traffic_sources.top) {
        const top = data.traffic_sources.top;
        const revenue = formatters.currency(top.revenue || 0);
        tsTop.innerHTML = `${top.name} <span style="color: var(--roi-positive)">(${revenue})</span>`;
    } else if (tsTop) {
        tsTop.textContent = '-';
    }

    // Топ оффер
    const topOffer = document.getElementById('topOffer');
    if (topOffer && data.offers && data.offers.top) {
        const top = data.offers.top;
        const revenue = formatters.currency(top.revenue || 0);
        topOffer.innerHTML = `${top.name} <span style="color: var(--roi-positive)">(${revenue})</span>`;
    } else if (topOffer) {
        topOffer.textContent = '-';
    }

    // Топ партнерка
    const topNetwork = document.getElementById('topNetwork');
    if (topNetwork && data.networks && data.networks.top) {
        const top = data.networks.top;
        const revenue = formatters.currency(top.revenue || 0);
        topNetwork.innerHTML = `${top.name} <span style="color: var(--roi-positive)">(${revenue})</span>`;
    } else if (topNetwork) {
        topNetwork.textContent = '-';
    }
}

/**
 * Загрузка топ кампаний
 */
async function loadTopCampaigns() {
    try {
        const cacheKey = `top_campaigns_${currentPeriod}_${currentSortBy}`;
        let data = cache.get(cacheKey);

        if (!data) {
            data = await api.get(`/campaigns/top?period=${currentPeriod}&limit=5&sort_by=${currentSortBy}`);
            cache.set(cacheKey, data);
        }

        updateTopCampaignsTable(data);
    } catch (error) {
        console.error('Failed to load top campaigns:', error);
        toast.error('Ошибка загрузки топ кампаний');
    }
}

/**
 * Обновление таблицы топ кампаний
 */
function updateTopCampaignsTable(data) {
    const container = document.getElementById('topCampaignsTable');
    if (!container) return;

    // Извлекаем массив кампаний из ответа API
    const campaigns = data.campaigns || [];

    if (campaigns.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 2rem;">Нет данных</p>';
        return;
    }

    // Состояние сортировки
    const sortState = {column: null, direction: 'asc'};

    const render = () => {
        let html = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Кампания</th>
                            ${renderSortableHeader('roi', 'ROI', 'number', sortState.column, sortState.direction)}
                            ${renderSortableHeader('cost', 'Расход', 'number', sortState.column, sortState.direction)}
                            ${renderSortableHeader('revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                            ${renderSortableHeader('profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                            ${renderSortableHeader('clicks', 'Клики', 'number', sortState.column, sortState.direction)}
                            ${renderSortableHeader('leads', 'Лиды', 'number', sortState.column, sortState.direction)}
                            <th>Binom</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        campaigns.forEach(c => {
            const profit = (c.revenue || 0) - (c.cost || 0);
            const binomId = c.binom_id || c.id;

            html += `
                <tr>
                    <td><strong>${c.name || 'N/A'}</strong></td>
                    <td style="color: ${c.roi > 0 ? 'var(--roi-positive)' : 'var(--roi-negative)'}">
                        ${c.roi ? formatters.percent(c.roi) : '0%'}
                    </td>
                    <td>${formatters.currency(c.cost || 0)}</td>
                    <td>${formatters.currency(c.revenue || 0)}</td>
                    <td style="color: ${profit > 0 ? 'var(--roi-positive)' : 'var(--roi-negative)'}">
                        ${formatters.currency(profit)}
                    </td>
                    <td>${formatters.number(c.clicks || 0)}</td>
                    <td>${formatters.number(c.leads || 0)}</td>
                    <td>${renderBinomLink(binomId)}</td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        container.innerHTML = html;

        // Подключаем сортировку
        if (typeof attachTableSortHandlers === 'function') {
            attachTableSortHandlers(container, campaigns, (col, dir) => render(), sortState);
        }
    };

    render();
}

/**
 * Загрузка последних алертов
 */
async function loadRecentAlerts() {
    try {
        const cacheKey = 'recent_alerts';
        let data = cache.get(cacheKey);

        if (!data) {
            // Увеличиваем лимит и запрашиваем все severity levels для разделения по категориям
            data = await api.get('/alerts/recent?limit=30&severity_filter=all');
            cache.set(cacheKey, data);
        }

        updateRecentAlerts(data.alerts || []);
    } catch (error) {
        console.error('Failed to load recent alerts:', error);
    }
}

/**
 * Обновление последних алертов (разделение по категориям)
 */
function updateRecentAlerts(alerts) {
    const criticalContainer = document.getElementById('criticalAlerts');
    const highContainer = document.getElementById('highAlerts');
    const mediumContainer = document.getElementById('mediumAlerts');

    if (!criticalContainer || !highContainer || !mediumContainer) return;

    // Логируем для отладки
    console.log('Total alerts received:', alerts.length);
    console.log('Severity distribution:', alerts.reduce((acc, a) => {
        acc[a.severity] = (acc[a.severity] || 0) + 1;
        return acc;
    }, {}));

    // Разделяем по severity
    const critical = alerts.filter(a => a.severity === 'critical').slice(0, 5);
    const high = alerts.filter(a => a.severity === 'high').slice(0, 5);
    const medium = alerts.filter(a => a.severity === 'medium' || a.severity === 'info').slice(0, 5);

    console.log('Filtered counts - critical:', critical.length, 'high:', high.length, 'medium:', medium.length);

    // Рендерим для каждой категории
    criticalContainer.innerHTML = critical.length > 0
        ? critical.map(alert => renderRecentAlert(alert)).join('')
        : '<p style="text-align: center; color: var(--text-muted); padding: 2rem; font-size: 0.875rem;">Нет критичных алертов</p>';

    highContainer.innerHTML = high.length > 0
        ? high.map(alert => renderRecentAlert(alert)).join('')
        : '<p style="text-align: center; color: var(--text-muted); padding: 2rem; font-size: 0.875rem;">Нет важных алертов</p>';

    mediumContainer.innerHTML = medium.length > 0
        ? medium.map(alert => renderRecentAlert(alert)).join('')
        : '<p style="text-align: center; color: var(--text-muted); padding: 2rem; font-size: 0.875rem;">Нет средних алертов</p>';
}

/**
 * Рендер одного алерта для дашборда (кликабельный, компактный)
 */
function renderRecentAlert(alert) {
    const severityClass = alert.severity || 'medium';
    const time = alert.created_at ? new Date(alert.created_at).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    }) : 'Только что';

    // Форматируем название модуля
    const moduleName = formatModuleName(alert.module_id || 'unknown');
    const moduleUrl = alert.module_id ? `/modules/${alert.module_id}` : '#';

    // Сокращаем сообщение для дашборда (первые 100 символов)
    const shortMessage = (alert.message || 'Нет описания').substring(0, 100);
    const displayMessage = shortMessage.length < (alert.message || '').length
        ? shortMessage + '...'
        : shortMessage;

    return `
        <div class="alert-item-compact ${severityClass}"
             onclick="window.location.href='${moduleUrl}'"
             style="cursor: pointer; padding: 0.625rem; border-bottom: 1px solid var(--border-color); transition: background-color 0.2s;"
             onmouseover="this.style.backgroundColor='var(--bg-hover)'"
             onmouseout="this.style.backgroundColor='transparent'"
             title="Открыть модуль ${moduleName}">
            <div style="font-size: 0.8125rem; color: var(--text-primary); margin-bottom: 0.25rem; line-height: 1.4;">${displayMessage}</div>
            <div style="font-size: 0.6875rem; color: var(--text-muted); display: flex; justify-content: space-between; gap: 0.5rem;">
                <span style="font-weight: 500;">${moduleName}</span>
                <span>${time}</span>
            </div>
        </div>
    `;
}

/**
 * Загрузка названий модулей
 */
async function loadModuleNames() {
    try {
        const data = await api.get('/modules');
        if (data && data.modules) {
            // Создаем маппинг module_id -> название
            data.modules.forEach(module => {
                dashboardModuleNames[module.id] = module.name;
            });
        }
    } catch (error) {
        console.error('Failed to load module names:', error);
    }
}

/**
 * Форматирование названия модуля
 */
function formatModuleName(moduleId) {
    // Используем русское название из маппинга, если доступно
    if (dashboardModuleNames[moduleId]) {
        return dashboardModuleNames[moduleId];
    }

    // Fallback: простое форматирование из ID
    return moduleId
        .replace(/_/g, ' ')
        .replace(/alert/gi, '')
        .trim()
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Обработчики событий
 */
async function initDashboard() {
    // Загружаем конфигурацию приложения (для Binom URL)
    if (typeof loadAppConfig === 'function') {
        await loadAppConfig();
    }

    // Загружаем названия модулей для корректного отображения в алертах
    await loadModuleNames();

    // Селектор периода
    const periodBtns = document.querySelectorAll('.period-btn');
    periodBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            periodBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentPeriod = btn.dataset.period;

            // Перезагружаем данные
            cache.clear(); // Очищаем кеш для нового периода
            loadStats();
            loadSummaryInfo();
            loadTopCampaigns();
            loadCharts();
        });
    });

    // Вкладки сортировки топ кампаний
    const tabBtns = document.querySelectorAll('.top-campaigns-tabs .tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.top-campaigns-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSortBy = btn.dataset.sort;

            // Перезагружаем топ кампании
            cache.clear(); // Очищаем кеш для новой сортировки
            loadTopCampaigns();
        });
    });

    // Вкладки для переключения метрик в Momentum Chart
    const momentumTabBtns = document.querySelectorAll('.momentum-tabs .tab-btn');
    momentumTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Обновляем активное состояние
            document.querySelectorAll('.momentum-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Обновляем текущую метрику
            currentMomentumMetric = btn.dataset.metric;

            // Перерисовываем график с новой метрикой
            if (momentumData) {
                createMomentumChart(momentumData, currentMomentumMetric);
            }
        });
    });

    // Вкладки для переключения метрик в Sparkline Chart
    const sparklineTabBtns = document.querySelectorAll('.sparkline-tabs .tab-btn');
    sparklineTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Обновляем активное состояние
            document.querySelectorAll('.sparkline-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Обновляем текущую метрику
            currentSparklineMetric = btn.dataset.metric;

            // Перерисовываем график с новой метрикой
            if (sparklineData) {
                createSparklineChart(sparklineData, currentSparklineMetric);
            }
        });
    });

    // Загружаем данные
    loadStats();
    loadSummaryInfo();
    loadTopCampaigns();
    loadRecentAlerts();
    loadCharts();

    // Автообновление каждые 5 минут
    setInterval(() => {
        cache.clear();
        loadStats();
        loadTopCampaigns();
        loadRecentAlerts();
        loadCharts();
        toast.info('Данные обновлены');
    }, 300000);
}

/**
 * Загрузка данных для графиков
 */
async function loadCharts() {
    try {
        const cacheKey = `charts_${currentPeriod}`;
        let data = cache.get(cacheKey);

        if (!data) {
            data = await api.get(`/stats/charts?period=${currentPeriod}`);
            cache.set(cacheKey, data);
        }

        // Данные уже приходят в правильном порядке (от старых к новым)
        const roiData = data.roi_by_days || [];

        createROIChart(roiData);
        createSpendChart(data.spend_distribution || []);
        createRevenueChart(data.revenue_distribution || []);
        createTrendChart(roiData);

        // Для графика сравнения периодов (Momentum Chart)
        loadPeriodComparisonForMomentum();
    } catch (error) {
        console.error('Failed to load charts:', error);
    }
}

/**
 * Создание графика ROI по дням
 */
function createROIChart(data) {
    const canvas = document.getElementById('roiChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (roiChart) {
            roiChart.destroy();
            roiChart = null;
        }
    } catch (error) {
        console.error('Error destroying roiChart:', error);
        roiChart = null;
    }

    // Проверка на пустые данные
    if (!data || data.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Подготовка данных
    const labels = data.map(item => formatters.date(item.date));
    const roiValues = data.map(item => item.roi || 0);

    // Получаем CSS переменные для цветов
    const rootStyles = getComputedStyle(document.documentElement);
    const positiveColor = rootStyles.getPropertyValue('--roi-positive').trim() || '#10b981';
    const negativeColor = rootStyles.getPropertyValue('--roi-negative').trim() || '#ef4444';
    const accentColor = rootStyles.getPropertyValue('--accent-primary').trim() || '#005cb7';

    // Динамическое окрашивание точек в зависимости от значения ROI
    const pointColors = roiValues.map(roi => {
        if (roi > 0) return positiveColor;
        if (roi < 0) return negativeColor;
        return accentColor;
    });

    try {
        roiChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'ROI, %',
                    data: roiValues,
                    borderColor: accentColor,
                    backgroundColor: `${accentColor}20`,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: pointColors,
                    pointBorderColor: '#1E1E1E',
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: '#e4e4e7',
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#2C2C2C',
                        titleColor: '#EDEDED',
                        bodyColor: '#B0B0B0',
                        borderColor: '#3A3A3A',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                return 'ROI: ' + context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: '#27272a',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            maxRotation: 45,
                            minRotation: 0
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating roiChart:', error);
        if (roiChart) {
            roiChart.destroy();
            roiChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Создание круговой диаграммы распределения расходов
 */
function createSpendChart(data) {
    const canvas = document.getElementById('spendChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (spendChart) {
            spendChart.destroy();
            spendChart = null;
        }
    } catch (error) {
        console.error('Error destroying spendChart:', error);
        spendChart = null;
    }

    // Проверка на пустые данные
    if (!data || data.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Подготовка данных
    const labels = data.map(item => item.name || 'Без названия');
    const values = data.map(item => item.cost || 0);

    // Генерация цветов - фиолетово-синие градиенты
    const colors = [
        '#6C63FF', '#A0AFFF', '#8B83FF', '#5A52E0', '#7B73E8',
        '#6C63FF', '#A0AFFF', '#8B83FF', '#5A52E0', '#7B73E8'
    ];

    try {
        spendChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, values.length),
                borderColor: '#1E1E1E',
                borderWidth: 2,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#e4e4e7',
                        font: {
                            size: 11
                        },
                        padding: 10,
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: '#2C2C2C',
                    titleColor: '#EDEDED',
                    bodyColor: '#B0B0B0',
                    borderColor: '#3A3A3A',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = formatters.currency(context.parsed);
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return label + ': ' + value + ' (' + percentage + '%)';
                        }
                    }
                }
            }
        }
    });
    } catch (error) {
        console.error('Error creating spendChart:', error);
        if (spendChart) {
            spendChart.destroy();
            spendChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Создание круговой диаграммы распределения доходов по партнеркам
 */
function createRevenueChart(data) {
    const canvas = document.getElementById('revenueChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (revenueChart) {
            revenueChart.destroy();
            revenueChart = null;
        }
    } catch (error) {
        console.error('Error destroying revenueChart:', error);
        revenueChart = null;
    }

    // Проверка на пустые данные
    if (!data || data.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Подготовка данных
    const labels = data.map(item => item.name || 'Без названия');
    const values = data.map(item => item.revenue || 0);

    // Генерация цветов - зеленые градиенты
    const colors = [
        '#10b981', '#34d399', '#6ee7b7', '#059669', '#14b8a6',
        '#10b981', '#34d399', '#6ee7b7', '#059669', '#14b8a6'
    ];

    try {
        revenueChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, values.length),
                borderColor: '#1E1E1E',
                borderWidth: 2,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#e4e4e7',
                        font: {
                            size: 11
                        },
                        padding: 10,
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: '#2C2C2C',
                    titleColor: '#EDEDED',
                    bodyColor: '#B0B0B0',
                    borderColor: '#3A3A3A',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = formatters.currency(context.parsed);
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return label + ': ' + value + ' (' + percentage + '%)';
                        }
                    }
                }
            }
        }
    });
    } catch (error) {
        console.error('Error creating revenueChart:', error);
        if (revenueChart) {
            revenueChart.destroy();
            revenueChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Создание area chart для трендов доходов и расходов
 */
function createTrendChart(data) {
    const canvas = document.getElementById('trendChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (trendChart) {
            trendChart.destroy();
            trendChart = null;
        }
    } catch (error) {
        console.error('Error destroying trendChart:', error);
        trendChart = null;
    }

    // Проверка на пустые данные
    if (!data || data.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    // Подготовка данных
    const labels = data.map(item => formatters.date(item.date));
    const costValues = data.map(item => item.cost || 0);
    const revenueValues = data.map(item => item.revenue || 0);

    try {
        trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Расходы',
                    data: costValues,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#ef4444',
                    pointBorderColor: '#1E1E1E',
                    pointBorderWidth: 2
                },
                {
                    label: 'Доходы',
                    data: revenueValues,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#10b981',
                    pointBorderColor: '#1E1E1E',
                    pointBorderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#e4e4e7',
                        font: {
                            size: 12
                        },
                        usePointStyle: true,
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: '#2C2C2C',
                    titleColor: '#EDEDED',
                    bodyColor: '#B0B0B0',
                    borderColor: '#3A3A3A',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + formatters.currency(context.parsed.y);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#27272a',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        maxRotation: 45,
                        minRotation: 0
                    }
                }
            }
        }
    });
    } catch (error) {
        console.error('Error creating trendChart:', error);
        if (trendChart) {
            trendChart.destroy();
            trendChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Загрузка данных для сравнения периодов (все три графика)
 */
async function loadPeriodComparisonForMomentum() {
    try {
        const cacheKey = `period_comparison_${currentPeriod}`;
        let data = cache.get(cacheKey);

        if (!data) {
            data = await api.get(`/dashboard/period-comparison?period=${currentPeriod}`);
            cache.set(cacheKey, data);
        }

        // Сохраняем данные для переключения табов
        momentumData = data;
        sparklineData = data.sparklines;

        createMomentumChart(data, currentMomentumMetric);
        createDeltaChart(data);
        createSparklineChart(data.sparklines, currentSparklineMetric);
    } catch (error) {
        console.error('Failed to load period comparison:', error);
    }
}

/**
 * Создание Momentum Chart - сравнение текущего и предыдущего периода по одной метрике
 */
function createMomentumChart(data, metric = 'roi') {
    const canvas = document.getElementById('comparisonChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (comparisonChart) {
            comparisonChart.destroy();
            comparisonChart = null;
        }
    } catch (error) {
        console.error('Error destroying comparisonChart:', error);
        comparisonChart = null;
    }

    // Проверка на пустые данные
    if (!data || !data.current) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    const current = data.current;
    const previous = data.previous;
    const deltas = data.deltas;
    const periodInfo = data.period_info;

    // Выбираем данные для отображаемой метрики
    let label = '';
    let currentValue = 0;
    let previousValue = 0;
    let delta = 0;
    let formatter = (v) => v.toFixed(2);

    switch (metric) {
        case 'roi':
            label = 'ROI';
            currentValue = current.roi;
            previousValue = previous.roi;
            delta = deltas.roi;
            formatter = (v) => v.toFixed(2) + '%';
            break;
        case 'revenue':
            label = 'Доход';
            currentValue = current.revenue;
            previousValue = previous.revenue;
            delta = deltas.revenue;
            formatter = (v) => formatters.currency(v);
            break;
        case 'profit':
            label = 'Профит';
            currentValue = current.profit || 0;
            previousValue = previous.profit || 0;
            delta = deltas.profit || 0;
            formatter = (v) => formatters.currency(v);
            break;
        case 'clicks':
            label = 'Клики';
            currentValue = current.clicks;
            previousValue = previous.clicks;
            delta = deltas.clicks;
            formatter = (v) => formatters.number(v);
            break;
        case 'cr':
            label = 'CR';
            currentValue = current.cr;
            previousValue = previous.cr;
            delta = deltas.cr;
            formatter = (v) => v.toFixed(2) + '%';
            break;
        default:
            label = 'ROI';
            currentValue = current.roi;
            previousValue = previous.roi;
            delta = deltas.roi;
            formatter = (v) => v.toFixed(2) + '%';
    }

    // Цвет для текущего периода (зеленый если рост, красный если падение)
    const currentColor = delta >= 0 ? '#10b981' : '#ef4444';

    // Форматирование дат для tooltip
    const formatDate = (dateStr) => {
        const date = new Date(dateStr);
        return `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}`;
    };

    const currentPeriodLabel = periodInfo
        ? `${formatDate(periodInfo.current_from)} - ${formatDate(periodInfo.current_to)}`
        : 'Текущий период';
    const previousPeriodLabel = periodInfo
        ? `${formatDate(periodInfo.previous_from)} - ${formatDate(periodInfo.previous_to)}`
        : 'Предыдущий период';

    try {
        comparisonChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Предыдущий период', 'Текущий период'],
                datasets: [{
                    label: label,
                    data: [previousValue, currentValue],
                    backgroundColor: ['#6b7280', currentColor],
                    borderColor: ['#6b7280', currentColor],
                    borderWidth: 2,
                    borderRadius: 6,
                    hoverBackgroundColor: ['#6b7280dd', currentColor + 'dd']
                }]
            },
            options: {
                indexAxis: 'y', // Горизонтальные бары
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#2C2C2C',
                        titleColor: '#EDEDED',
                        bodyColor: '#B0B0B0',
                        borderColor: '#3A3A3A',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            title: function(context) {
                                const periodLabel = context[0].label;
                                if (periodLabel === 'Текущий период') {
                                    return `Текущий период (${currentPeriodLabel})`;
                                } else {
                                    return `Предыдущий период (${previousPeriodLabel})`;
                                }
                            },
                            label: function(context) {
                                const value = context.parsed.x;
                                const formattedValue = formatter(value);
                                const periodLabel = context.label;

                                // Показываем дельту только для текущего периода
                                if (periodLabel === 'Текущий период') {
                                    const deltaSign = delta >= 0 ? '+' : '';
                                    const deltaValue = (delta !== null && delta !== undefined) ? delta.toFixed(2) : '0.00';
                                    return [
                                        `${label}: ${formattedValue}`,
                                        `Изменение: ${deltaSign}${deltaValue}%`
                                    ];
                                } else {
                                    return `${label}: ${formattedValue}`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: {
                            color: '#27272a',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            callback: function(value) {
                                return formatter(value);
                            }
                        }
                    },
                    y: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: {
                                size: 12
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating momentum chart:', error);
        if (comparisonChart) {
            comparisonChart.destroy();
            comparisonChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Создание Delta Chart - горизонтальный график изменений в процентах
 */
function createDeltaChart(data) {
    const canvas = document.getElementById('deltaChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (deltaChart) {
            deltaChart.destroy();
            deltaChart = null;
        }
    } catch (error) {
        console.error('Error destroying deltaChart:', error);
        deltaChart = null;
    }

    // Проверка на пустые данные
    if (!data || !data.deltas) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    const deltas = data.deltas;
    const current = data.current;
    const previous = data.previous;
    const periodInfo = data.period_info;

    // Метрики и их дельты
    const labels = ['ROI', 'Доход', 'Прибыль', 'Клики', 'CR', 'Расход', 'Апрув %'];
    const values = [
        deltas.roi || 0,
        deltas.revenue || 0,
        deltas.profit || 0,
        deltas.clicks || 0,
        deltas.cr || 0,
        deltas.cost || 0,
        deltas.approve_rate || 0
    ];

    // Цвета в зависимости от значения (зеленый = рост, красный = падение)
    const colors = values.map(v => v >= 0 ? '#10b981' : '#ef4444');

    // Форматирование дат для tooltip
    const formatDate = (dateStr) => {
        const date = new Date(dateStr);
        return `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}`;
    };

    const currentPeriodLabel = periodInfo
        ? `${formatDate(periodInfo.current_from)} - ${formatDate(periodInfo.current_to)}`
        : 'Текущий период';
    const previousPeriodLabel = periodInfo
        ? `${formatDate(periodInfo.previous_from)} - ${formatDate(periodInfo.previous_to)}`
        : 'Предыдущий период';

    try {
        deltaChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Изменение',
                    data: values,
                    backgroundColor: colors,
                    borderColor: colors,
                    borderWidth: 2,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y', // Горизонтальные столбцы
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#2C2C2C',
                        titleColor: '#EDEDED',
                        bodyColor: '#B0B0B0',
                        borderColor: '#3A3A3A',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            title: function(context) {
                                return context[0].label; // Название метрики
                            },
                            label: function(context) {
                                const deltaValue = context.parsed.x;
                                const metricIndex = context.dataIndex;
                                const sign = deltaValue >= 0 ? '+' : '';

                                // Получаем текущие и предыдущие значения для каждой метрики
                                let currentVal, previousVal, formatter, deltaUnit;

                                switch (metricIndex) {
                                    case 0: // ROI
                                        currentVal = current.roi;
                                        previousVal = previous.roi;
                                        formatter = (v) => v.toFixed(2) + '%';
                                        deltaUnit = ' п.п.'; // процентные пункты
                                        break;
                                    case 1: // Доход
                                        currentVal = current.revenue;
                                        previousVal = previous.revenue;
                                        formatter = (v) => formatters.currency(v);
                                        deltaUnit = '%';
                                        break;
                                    case 2: // Прибыль
                                        currentVal = current.profit || 0;
                                        previousVal = previous.profit || 0;
                                        formatter = (v) => formatters.currency(v);
                                        deltaUnit = '%';
                                        break;
                                    case 3: // Клики
                                        currentVal = current.clicks;
                                        previousVal = previous.clicks;
                                        formatter = (v) => formatters.number(v);
                                        deltaUnit = '%';
                                        break;
                                    case 4: // CR
                                        currentVal = current.cr;
                                        previousVal = previous.cr;
                                        formatter = (v) => v.toFixed(2) + '%';
                                        deltaUnit = ' п.п.'; // процентные пункты
                                        break;
                                    case 5: // Расход
                                        currentVal = current.cost;
                                        previousVal = previous.cost;
                                        formatter = (v) => formatters.currency(v);
                                        deltaUnit = '%';
                                        break;
                                    case 6: // Апрув %
                                        currentVal = current.approve_rate;
                                        previousVal = previous.approve_rate;
                                        formatter = (v) => v.toFixed(2) + '%';
                                        deltaUnit = ' п.п.'; // процентные пункты
                                        break;
                                }

                                return [
                                    `Текущий (${currentPeriodLabel}): ${formatter(currentVal)}`,
                                    `Предыдущий (${previousPeriodLabel}): ${formatter(previousVal)}`,
                                    `Изменение: ${sign}${deltaValue.toFixed(2)}${deltaUnit}`
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: '#27272a',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    },
                    y: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#a1a1aa'
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating delta chart:', error);
        if (deltaChart) {
            deltaChart.destroy();
            deltaChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

/**
 * Создание Sparkline Chart - ежедневный тренд одной метрики
 */
function createSparklineChart(sparklines, metric = 'roi') {
    const canvas = document.getElementById('sparklineChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Уничтожаем предыдущий график
    try {
        if (sparklineChart) {
            sparklineChart.destroy();
            sparklineChart = null;
        }
    } catch (error) {
        console.error('Error destroying sparklineChart:', error);
        sparklineChart = null;
    }

    // Проверка на пустые данные
    if (!sparklines || sparklines.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    const labels = sparklines.map(s => {
        const date = new Date(s.date);
        return `${date.getDate()}/${date.getMonth() + 1}`;
    });

    // Выбираем данные для отображаемой метрики
    let label = '';
    let data = [];
    let color = '#3b82f6';
    let formatter = (v) => v.toFixed(2);

    switch (metric) {
        case 'clicks':
            label = 'Клики';
            data = sparklines.map(s => s.clicks);
            color = '#3b82f6';
            formatter = (v) => formatters.number(v);
            break;
        case 'leads':
            label = 'Лиды';
            data = sparklines.map(s => s.leads);
            color = '#10b981';
            formatter = (v) => formatters.number(v);
            break;
        case 'profit':
            label = 'Профит';
            data = sparklines.map(s => s.profit || 0);
            color = '#06b6d4';
            formatter = (v) => formatters.currency(v);
            break;
        case 'cr':
            label = 'CR';
            data = sparklines.map(s => s.cr);
            color = '#8b5cf6';
            formatter = (v) => v.toFixed(2) + '%';
            break;
        case 'campaigns':
            label = 'Кампании';
            data = sparklines.map(s => s.campaigns);
            color = '#f59e0b';
            formatter = (v) => formatters.number(v);
            break;
        default:
            label = 'Клики';
            data = sparklines.map(s => s.clicks);
            color = '#3b82f6';
            formatter = (v) => formatters.number(v);
    }

    try {
        sparklineChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: label,
                    data: data,
                    borderColor: color,
                    backgroundColor: `${color}20`,
                    borderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: color,
                    pointBorderColor: '#1E1E1E',
                    pointBorderWidth: 1,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: '#2C2C2C',
                        titleColor: '#EDEDED',
                        bodyColor: '#B0B0B0',
                        borderColor: '#3A3A3A',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false,
                        callbacks: {
                            label: function(context) {
                                const value = context.parsed.y;
                                return `${label}: ${formatter(value)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: {
                                size: 10
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: '#27272a',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#a1a1aa',
                            font: {
                                size: 10
                            },
                            callback: function(value) {
                                return formatter(value);
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating sparkline chart:', error);
        if (sparklineChart) {
            sparklineChart.destroy();
            sparklineChart = null;
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Ошибка создания графика', canvas.width / 2, canvas.height / 2);
    }
}

// Инициализация при загрузке страницы
if (window.location.pathname === '/' || window.location.pathname === '/index.html') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDashboard);
    } else {
        // DOM уже загружен
        initDashboard();
    }
}
