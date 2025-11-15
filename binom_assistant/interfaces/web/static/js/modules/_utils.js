/**
 * Утилиты для модульной системы
 * Общие функции для рендера таблиц, сортировки и т.д.
 */

// Глобальная конфигурация приложения
const AppConfig = {
    binomUrl: null,
    loaded: false
};

/**
 * Загружает конфигурацию приложения с сервера
 * @returns {Promise<Object>}
 */
async function loadAppConfig() {
    if (AppConfig.loaded) {
        return AppConfig;
    }

    try {
        const config = await api.get('/system/config');
        AppConfig.binomUrl = config.binom_url;
        AppConfig.loaded = true;
        console.log('App config loaded:', AppConfig);
        return AppConfig;
    } catch (error) {
        console.error('Failed to load app config:', error);
        // Fallback
        AppConfig.binomUrl = 'http://localhost';
        AppConfig.loaded = true;
        return AppConfig;
    }
}

/**
 * Получает URL Binom
 * @returns {string}
 */
function getBinomUrl() {
    return AppConfig.binomUrl || 'http://localhost';
}

/**
 * Создает ссылку на кампанию в Bином
 * @param {string|number} binomId - ID кампании в Binom
 * @returns {string}
 */
function getBinomCampaignLink(binomId) {
    const binomUrl = getBinomUrl();
    // binomUrl уже содержит полный путь с API файлом (например, http://tracker.com/index.php)
    // Добавляем только параметры запроса
    return `${binomUrl}?page=Stats&camp_id=${binomId}&group1=31&group2=1&group3=1&date=3`;
}

/**
 * Создает иконку-ссылку на Binom
 * @param {string|number} binomId - ID кампании в Binom
 * @returns {string} HTML строка
 */
function renderBinomLink(binomId) {
    const link = getBinomCampaignLink(binomId);
    return `<a href="${link}" target="_blank" title="Открыть кампанию в Binom" class="binom-link">
        <img src="/static/icons/binom.png" width="16" height="16" alt="Binom">
    </a>`;
}

/**
 * Форматирует значение ROI с подсветкой
 * @param {number} roi - ROI в процентах
 * @param {number} decimals - Количество знаков после запятой
 * @returns {string} HTML строка
 */
function formatROI(roi, decimals = 2) {
    const className = roi < 0 ? 'text-danger' : 'text-success';
    return `<span class="${className}">${roi.toFixed(decimals)}%</span>`;
}

/**
 * Форматирует число с разделителями тысяч
 * @param {number} value - Числовое значение
 * @param {number} decimals - Количество знаков после запятой
 * @returns {string}
 */
function formatNumber(value, decimals = 0) {
    if (value === null || value === undefined) {
        return '0';
    }
    return value.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Форматирует денежное значение
 * @param {number} value - Значение в долларах
 * @param {number} decimals - Количество знаков после запятой
 * @returns {string}
 */
function formatCurrency(value, decimals = 2) {
    return `$${value.toFixed(decimals)}`;
}

/**
 * Форматирует прибыль/убыток с подсветкой
 * @param {number} profit - Прибыль (revenue - cost)
 * @param {number} decimals - Количество знаков после запятой
 * @returns {string} HTML строка
 */
function formatProfit(profit, decimals = 2) {
    const className = profit >= 0 ? 'text-success' : 'text-danger';
    return `<span class="${className}">${formatCurrency(profit, decimals)}</span>`;
}

/**
 * Форматирует severity badge
 * @param {string} severity - critical, high, medium
 * @returns {string} HTML строка
 */
function formatSeverity(severity) {
    return `<span class="severity-badge severity-${severity}">${severity}</span>`;
}

/**
 * Создает sortable заголовок таблицы
 * @param {string} column - Имя колонки
 * @param {string} label - Отображаемый текст
 * @param {string} type - Тип данных (number, string, severity)
 * @param {string|null} currentSortColumn - Текущая колонка сортировки
 * @param {string} currentSortDirection - Текущее направление (asc/desc)
 * @returns {string} HTML строка
 */
function renderSortableHeader(column, label, type, currentSortColumn, currentSortDirection) {
    const indicator = currentSortColumn === column
        ? (currentSortDirection === 'asc' ? ' ▲' : ' ▼')
        : '';
    return `<th class="sortable" data-column="${column}" data-type="${type}">${label}${indicator}</th>`;
}

/**
 * Сортирует массив данных
 * @param {Array} data - Массив для сортировки
 * @param {string} column - Колонка для сортировки
 * @param {string} type - Тип данных (number, string, severity)
 * @param {string} direction - Направление (asc/desc)
 * @returns {Array} Отсортированный массив
 */
function sortData(data, column, type, direction) {
    return data.sort((a, b) => {
        let valA, valB;

        if (column === 'profit') {
            // Вычисляем прибыль для сортировки
            valA = a.total_revenue - a.total_cost;
            valB = b.total_revenue - b.total_cost;
        } else if (type === 'severity') {
            // Сортировка по severity: critical > high > medium
            const severityOrder = { critical: 3, high: 2, medium: 1 };
            valA = severityOrder[a[column]] || 0;
            valB = severityOrder[b[column]] || 0;
        } else {
            valA = a[column];
            valB = b[column];
        }

        // Обработка undefined/null
        if (valA === undefined || valA === null) valA = type === 'number' ? 0 : '';
        if (valB === undefined || valB === null) valB = type === 'number' ? 0 : '';

        // Сравнение
        let comparison = 0;
        if (type === 'number' || type === 'severity') {
            comparison = valA - valB;
        } else {
            comparison = String(valA).localeCompare(String(valB));
        }

        return direction === 'asc' ? comparison : -comparison;
    });
}

/**
 * Подключает обработчики сортировки к таблице
 * @param {HTMLElement} container - Контейнер таблицы
 * @param {Array} data - Массив данных
 * @param {Function} rerenderCallback - Функция для перерисовки таблицы (принимает column, direction)
 * @param {Object} sortState - Объект с текущим состоянием сортировки {column, direction}
 */
function attachTableSortHandlers(container, data, rerenderCallback, sortState = {column: null, direction: 'asc'}) {
    const headers = container.querySelectorAll('th.sortable');

    headers.forEach(header => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            const column = header.getAttribute('data-column');
            const type = header.getAttribute('data-type');

            // Переключаем направление если кликнули по той же колонке
            if (sortState.column === column) {
                sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
            } else {
                sortState.column = column;
                sortState.direction = 'asc';
            }

            // Сортируем данные
            sortData(data, column, type, sortState.direction);

            // Перерисовываем таблицу
            rerenderCallback(sortState.column, sortState.direction);
        });
    });
}

/**
 * Создает и показывает простое модальное окно
 * @param {string} title - Заголовок окна
 * @param {string} content - HTML содержимое
 */
function showModal(title, content) {
    // Удаляем существующую модалку если есть
    const existingModal = document.getElementById('custom-modal');
    if (existingModal) {
        existingModal.remove();
    }

    // Создаем модальное окно
    const modal = document.createElement('div');
    modal.id = 'custom-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${title}</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                ${content}
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Закрытие по клику на overlay
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Показываем
    setTimeout(() => modal.classList.add('show'), 10);
}

/**
 * Закрывает модальное окно
 */
function closeModal() {
    const modal = document.getElementById('custom-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    }
}

/**
 * Экранирует HTML специальные символы для предотвращения XSS
 * @param {string} text - Текст для экранирования
 * @returns {string} Экранированный текст
 */
function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}
