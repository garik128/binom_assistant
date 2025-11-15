/**
 * Модули аналитики - управление списком модулей
 */

// Состояние приложения
const state = {
    modules: [],
    filteredModules: [],
    searchQuery: '',
    categoryFilter: 'all',
    statusFilter: 'all',
    favorites: []
};

// Ключи для localStorage
const FAVORITES_KEY = 'binom_module_favorites';
const STATUS_FILTER_KEY = 'binom_status_filter';
const COMPACT_VIEW_KEY = 'binom_compact_view';

// Иконки для категорий модулей (inline SVG)
const categoryIcons = {
    critical_alerts: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <line x1="12" y1="9" x2="12" y2="13"></line>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
    </svg>`,
    trend_analysis: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 3v18h18"></path>
        <path d="m19 9-5 5-4-4-3 3"></path>
    </svg>`,
    stability: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="m9 12 2 2 4-4"></path>
    </svg>`,
    predictive: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path>
        <path d="M22 12A10 10 0 0 0 12 2v10z"></path>
    </svg>`,
    problem_detection: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
    </svg>`,
    opportunities: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
    </svg>`,
    segmentation: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="7" height="7"></rect>
        <rect x="14" y="3" width="7" height="7"></rect>
        <rect x="14" y="14" width="7" height="7"></rect>
        <rect x="3" y="14" width="7" height="7"></rect>
    </svg>`,
    portfolio: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 7h-9M14 3v4M6 21V3h8v18M2 21h20"></path>
    </svg>`,
    sources_offers: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
    </svg>`
};

// Приоритеты модулей
const priorityLabels = {
    critical: 'Критический',
    high: 'Высокий',
    medium: 'Средний',
    low: 'Низкий'
};

const priorityColors = {
    critical: '#ef4444',
    high: '#a06604',
    medium: '#3b82f6',
    low: '#6b7280'
};

// Статусы модулей (enabled/disabled)
const statusLabels = {
    enabled: 'Включен',
    disabled: 'Выключен'
};

const statusColors = {
    enabled: '#10b981',
    disabled: '#6b7280'
};

/**
 * Функции работы с избранным (localStorage)
 */

// Загрузка избранного из localStorage
function loadFavorites() {
    try {
        const stored = localStorage.getItem(FAVORITES_KEY);
        state.favorites = stored ? JSON.parse(stored) : [];
    } catch (error) {
        console.error('Ошибка загрузки избранного:', error);
        state.favorites = [];
    }
}

// Сохранение избранного в localStorage
function saveFavorites() {
    try {
        localStorage.setItem(FAVORITES_KEY, JSON.stringify(state.favorites));
    } catch (error) {
        console.error('Ошибка сохранения избранного:', error);
    }
}

// Проверка, находится ли модуль в избранном
function isFavorite(moduleId) {
    return state.favorites.includes(moduleId);
}

// Добавление модуля в избранное
function addToFavorites(moduleId) {
    if (!isFavorite(moduleId)) {
        state.favorites.push(moduleId);
        saveFavorites();
        renderModules();
        renderFavorites();
        showSuccess('Модуль добавлен в избранное');
    }
}

// Удаление модуля из избранного
function removeFromFavorites(moduleId) {
    state.favorites = state.favorites.filter(id => id !== moduleId);
    saveFavorites();
    renderModules();
    renderFavorites();
    showSuccess('Модуль удален из избранного');
}

// Переключение избранного
function toggleFavorite(moduleId) {
    if (isFavorite(moduleId)) {
        removeFromFavorites(moduleId);
    } else {
        addToFavorites(moduleId);
    }
}

// Отрисовка блока избранного
function renderFavorites() {
    const section = document.getElementById('favoritesSection');
    const content = document.getElementById('favoritesContent');
    const count = document.getElementById('favoritesCount');

    if (state.favorites.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    count.textContent = state.favorites.length;

    // Фильтруем модули из избранного
    const favoriteModules = state.modules.filter(m => isFavorite(m.id));

    content.innerHTML = favoriteModules.map(module => renderModuleCard(module)).join('');

    // Добавляем обработчики событий для карточек в избранном
    attachModuleEventHandlers();
}

/**
 * Глобальный обработчик для кнопок избранного (event delegation)
 * Устанавливается один раз при загрузке страницы
 */
function setupGlobalFavoriteHandler() {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-favorite');
        if (btn) {
            e.stopPropagation();
            const moduleId = btn.dataset.moduleId;
            toggleFavorite(moduleId);
        }
    });
}

/**
 * Инициализация страницы
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Устанавливаем активный пункт меню
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-page') === 'analytics') {
            item.classList.add('active');
        }
    });

    // Загружаем избранное из localStorage
    loadFavorites();

    // Загружаем модули
    await loadModules();

    // Настраиваем фильтры и поиск
    setupFilters();

    // Настраиваем компактный вид
    setupCompactView();

    // Отрисовываем избранное
    renderFavorites();

    // Устанавливаем глобальный обработчик для кнопок избранного (event delegation)
    setupGlobalFavoriteHandler();

    // Скрываем loader
    hideLoader();
});

/**
 * Загрузка списка модулей с API
 */
async function loadModules() {
    try {
        const response = await api.get('/modules');
        state.modules = response.modules || [];
        state.filteredModules = [...state.modules];
        renderModules();
    } catch (error) {
        console.error('Ошибка загрузки модулей:', error);
        showError('Не удалось загрузить модули');
    }
}

/**
 * Настройка фильтров и поиска
 */
function setupFilters() {
    const searchInput = document.getElementById('moduleSearch');
    const categoryFilter = document.getElementById('categoryFilter');
    const statusFilter = document.getElementById('statusFilter');

    // Поиск с debounce
    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.searchQuery = e.target.value.toLowerCase();
            applyFilters();
        }, 300);
    });

    // Фильтр по категории
    categoryFilter.addEventListener('change', (e) => {
        state.categoryFilter = e.target.value;
        applyFilters();
    });

    // Фильтр по статусу
    statusFilter.addEventListener('change', (e) => {
        state.statusFilter = e.target.value;
        // Сохраняем выбор в localStorage
        try {
            localStorage.setItem(STATUS_FILTER_KEY, state.statusFilter);
        } catch (error) {
            console.warn('Failed to save status filter to localStorage:', error);
        }
        applyFilters();
    });

    // Восстанавливаем сохраненный фильтр из localStorage
    try {
        const savedFilter = localStorage.getItem(STATUS_FILTER_KEY);
        if (savedFilter && (savedFilter === 'all' || savedFilter === 'active' || savedFilter === 'inactive')) {
            state.statusFilter = savedFilter;
            statusFilter.value = savedFilter;
            // Применяем фильтр сразу после восстановления
            applyFilters();
        }
    } catch (error) {
        console.warn('Failed to load status filter from localStorage:', error);
    }
}

/**
 * Применение фильтров
 */
function applyFilters() {
    state.filteredModules = state.modules.filter(module => {
        // Фильтр по поиску
        const matchesSearch = !state.searchQuery ||
            module.name.toLowerCase().includes(state.searchQuery) ||
            module.description.toLowerCase().includes(state.searchQuery);

        // Фильтр по категории
        const matchesCategory = state.categoryFilter === 'all' ||
            module.category === state.categoryFilter;

        // Фильтр по статусу (активные/неактивные модули)
        let matchesStatus = true;
        if (state.statusFilter === 'active') {
            matchesStatus = module.enabled === true;
        } else if (state.statusFilter === 'inactive') {
            matchesStatus = module.enabled === false;
        }
        // Если 'all' - пропускаем все

        return matchesSearch && matchesCategory && matchesStatus;
    });

    renderModules();
}

/**
 * Отрисовка модулей
 */
function renderModules() {
    const container = document.getElementById('modulesContent');

    if (state.filteredModules.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                    <circle cx="11" cy="11" r="8"></circle>
                    <path d="m21 21-4.35-4.35"></path>
                </svg>
                <h3>Модули не найдены</h3>
                <p>Попробуйте изменить условия поиска или фильтры</p>
            </div>
        `;
        return;
    }

    // Группируем модули по категориям
    const groupedModules = groupByCategory(state.filteredModules);

    // Генерируем HTML
    let html = '';
    for (const [category, modules] of Object.entries(groupedModules)) {
        html += `
            <div class="module-category">
                <div class="category-header">
                    <div class="category-icon">${categoryIcons[category] || categoryIcons.optimization}</div>
                    <h2 class="category-title">${getCategoryName(category)}</h2>
                    <span class="category-count">${modules.length}</span>
                </div>
                <div class="modules-grid">
                    ${modules.map(module => renderModuleCard(module)).join('')}
                </div>
            </div>
        `;
    }

    container.innerHTML = html;

    // Добавляем обработчики событий
    attachModuleEventHandlers();
}

/**
 * Группировка модулей по категориям
 */
function groupByCategory(modules) {
    return modules.reduce((acc, module) => {
        const category = module.category || 'optimization';
        if (!acc[category]) {
            acc[category] = [];
        }
        acc[category].push(module);
        return acc;
    }, {});
}

/**
 * Получение названия категории
 */
function getCategoryName(category) {
    const names = {
        critical_alerts: 'Критические алерты',
        trend_analysis: 'Анализ трендов',
        stability: 'Стабильность',
        predictive: 'Предиктивная аналитика',
        problem_detection: 'Детекция проблем',
        opportunities: 'Поиск возможностей',
        segmentation: 'Группировка',
        portfolio: 'Портфельная аналитика',
        sources_offers: 'Источники и офферы'
    };
    return names[category] || 'Прочее';
}

/**
 * Отрисовка карточки модуля
 */
function renderModuleCard(module) {
    // Статус enabled/disabled
    const moduleStatus = module.enabled ? 'enabled' : 'disabled';
    const statusColor = statusColors[moduleStatus];
    const priorityColor = priorityColors[module.priority] || priorityColors.medium;
    const lastRun = module.last_run ? formatDate(module.last_run) : 'Никогда';

    // Ключевые метрики
    let metricsHtml = '';
    if (module.last_result && module.last_result.summary) {
        const summary = module.last_result.summary;
        metricsHtml = `
            <div class="module-metrics">
                ${Object.entries(summary).slice(0, 3).map(([key, value]) => `
                    <div class="metric-item">
                        <span class="metric-label">${formatMetricLabel(key, module.id)}:</span>
                        <span class="metric-value">${formatMetricValue(key, value)}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    return `
        <div class="module-card" data-module-id="${module.id}">
            <div class="module-card-header">
                <div class="module-card-title">
                    <h3>${module.name}</h3>
                    <span class="module-priority" style="background: ${priorityColor}">
                        ${priorityLabels[module.priority] || 'Средний'}
                    </span>
                </div>
                <div class="module-status-row">
                    <div class="module-status" style="color: ${statusColor}">
                        <span class="status-dot" style="background: ${statusColor}"></span>
                        ${statusLabels[moduleStatus]}
                    </div>
                    <button class="btn-favorite ${isFavorite(module.id) ? 'active' : ''}"
                            data-module-id="${module.id}"
                            title="${isFavorite(module.id) ? 'Удалить из избранного' : 'Добавить в избранное'}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="${isFavorite(module.id) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                        </svg>
                        <span>${isFavorite(module.id) ? 'В избранном' : 'В избранное'}</span>
                    </button>
                </div>
            </div>

            <p class="module-card-description">${module.description}</p>

            ${metricsHtml}

            <div class="module-card-footer">
                <div class="module-last-run">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    <span>Последний запуск: ${lastRun}</span>
                </div>

                <div class="module-actions">
                    ${module.status === 'running' ? `
                        <button class="btn-action btn-view" data-module-id="${module.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                            Просмотр
                        </button>
                    ` : `
                        <button class="btn-action btn-run" data-module-id="${module.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="5 3 19 12 5 21 5 3"></polygon>
                            </svg>
                            Запустить
                        </button>
                    `}

                    <button class="btn-action btn-settings" data-module-id="${module.id}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M12 1v6m0 6v10"></path>
                        </svg>
                        Настройки
                    </button>

                    <button class="btn-action btn-history" data-module-id="${module.id}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 3v5h5"></path>
                            <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"></path>
                        </svg>
                        История
                    </button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Подключение обработчиков событий к модулям
 */
function attachModuleEventHandlers() {
    // Клик по карточке - переход к деталям
    document.querySelectorAll('.module-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Игнорируем клики по кнопкам
            if (e.target.closest('.btn-action') || e.target.closest('.btn-favorite')) return;

            const moduleId = card.dataset.moduleId;
            window.location.href = `/modules/${moduleId}`;
        });
    });

    // Кнопка "Запустить"
    document.querySelectorAll('.btn-run').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const moduleId = btn.dataset.moduleId;
            await runModule(moduleId);
        });
    });

    // Кнопка "Просмотр"
    document.querySelectorAll('.btn-view').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const moduleId = btn.dataset.moduleId;
            window.location.href = `/modules/${moduleId}`;
        });
    });

    // Кнопка "Настройки"
    document.querySelectorAll('.btn-settings').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const moduleId = btn.dataset.moduleId;
            window.location.href = `/modules/${moduleId}#settings`;
        });
    });

    // Кнопка "История"
    document.querySelectorAll('.btn-history').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const moduleId = btn.dataset.moduleId;
            window.location.href = `/modules/${moduleId}#history`;
        });
    });
}

/**
 * Запуск модуля
 */
async function runModule(moduleId) {
    try {
        // Обновляем статус модуля на "running"
        updateModuleStatus(moduleId, 'running');

        // Отправляем запрос на запуск
        const response = await api.post(`/modules/${moduleId}/run`, {});

        if (response.status === 'success') {
            showSuccess(`Модуль успешно запущен`);

            // Перенаправляем на страницу деталей с открытой вкладкой результатов
            setTimeout(() => {
                window.location.href = `/modules/${moduleId}#results`;
            }, 1000);
        } else {
            updateModuleStatus(moduleId, 'error');
            showError('Ошибка при запуске модуля');
        }
    } catch (error) {
        console.error('Ошибка запуска модуля:', error);
        updateModuleStatus(moduleId, 'error');
        showError('Не удалось запустить модуль');
    }
}

/**
 * Обновление статуса модуля в UI
 */
function updateModuleStatus(moduleId, newStatus) {
    const module = state.modules.find(m => m.id === moduleId);
    if (module) {
        module.status = newStatus;
        renderModules();
    }
}

/**
 * Форматирование даты
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    // Меньше минуты
    if (diff < 60000) {
        return 'Только что';
    }

    // Меньше часа
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `${minutes} мин. назад`;
    }

    // Меньше суток
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours} ч. назад`;
    }

    // Форматируем дату
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Форматирование названия метрики.
 * Использует переводы из ModuleRegistry для модульности.
 * @param {string} key - Ключ метрики
 * @param {string} moduleId - ID модуля (опционально)
 * @returns {string} - Переведенное название метрики
 */
function formatMetricLabel(key, moduleId) {
    // Пытаемся получить перевод из модуля через Registry
    if (moduleId && typeof ModuleRegistry !== 'undefined') {
        const module = ModuleRegistry.get(moduleId);
        if (module && module.translations && module.translations[key]) {
            return module.translations[key];
        }
    }

    // Fallback: общие переводы только для базовых метрик
    const commonLabels = {
        total_found: 'Найдено',
        critical_count: 'Критических',
        high_count: 'Высокой критичности',
        medium_count: 'Средней критичности',
        campaigns_count: 'Кампаний',
        revenue: 'Доход',
        roi: 'ROI'
    };

    return commonLabels[key] || key.replace(/_/g, ' ');
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
    return value;
}

/**
 * Показать сообщение об успехе
 */
function showSuccess(message) {
    showToast(message, 'success');
}

/**
 * Показать сообщение об ошибке
 */
function showError(message) {
    showToast(message, 'error');
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

    // Удаляем через 3 секунды
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Скрыть loader
 */
function hideLoader() {
    const loader = document.getElementById('initial-loader');
    if (loader) {
        loader.classList.add('hidden');
    }
}

/**
 * Настройка компактного вида
 */
function setupCompactView() {
    const toggle = document.getElementById('compactViewToggle');
    const container = document.querySelector('.modules-container');
    const favoritesSection = document.getElementById('favoritesSection');

    if (!toggle || !container) {
        console.warn('Элементы компактного вида не найдены');
        return;
    }

    // Загружаем состояние из localStorage
    const isCompact = loadCompactViewState();
    toggle.checked = isCompact;
    applyCompactView(isCompact, container, favoritesSection);

    // Обработчик переключения
    toggle.addEventListener('change', (e) => {
        const isCompact = e.target.checked;
        saveCompactViewState(isCompact);
        applyCompactView(isCompact, container, favoritesSection);
    });
}

/**
 * Загрузка состояния компактного вида из localStorage
 */
function loadCompactViewState() {
    try {
        const stored = localStorage.getItem(COMPACT_VIEW_KEY);
        return stored === 'true';
    } catch (error) {
        console.error('Ошибка загрузки состояния компактного вида:', error);
        return false;
    }
}

/**
 * Сохранение состояния компактного вида в localStorage
 */
function saveCompactViewState(isCompact) {
    try {
        localStorage.setItem(COMPACT_VIEW_KEY, isCompact.toString());
    } catch (error) {
        console.error('Ошибка сохранения состояния компактного вида:', error);
    }
}

/**
 * Применение компактного вида
 */
function applyCompactView(isCompact, container, favoritesSection) {
    if (isCompact) {
        container.classList.add('compact-view');
        if (favoritesSection) {
            favoritesSection.classList.add('compact-view');
        }
    } else {
        container.classList.remove('compact-view');
        if (favoritesSection) {
            favoritesSection.classList.remove('compact-view');
        }
    }
}
