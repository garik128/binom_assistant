/**
 * Модуль: До безубыточности
 * Прогноз выхода в безубыточность (ROI = 0) для убыточных кампаний с положительным трендом
 */
(function() {
    const ProfitabilityHorizonModule = {
        id: 'profitability_horizon',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            negative_roi_count: 'С отрицательным ROI',
            with_positive_trend: 'С положительным трендом',
            breakeven_forecasts: 'Прогнозов выхода в ноль',
            avg_days_to_breakeven: 'Среднее время до безубыточности (дней)',
            fastest_breakeven: 'Быстрейший выход (дней)'
        },

        algorithm: `
            <ol>
                <li>Загрузка исторических данных ROI за последние 7-30 дней для каждой кампании</li>
                <li>Фильтрация кампаний с текущим ROI < 0 (убыточные)</li>
                <li>Построение линейной регрессии для определения тренда ROI</li>
                <li>Отбор только кампаний с положительным трендом (ROI растет)</li>
                <li>Расчет точки пересечения с нулем: дни = -intercept / slope</li>
                <li>Определение прогнозируемой даты выхода в безубыточность</li>
                <li>Расчет уверенности прогноза на основе R-squared</li>
                <li>Сортировка по времени до безубыточности (ASC)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Current ROI</strong> - текущий ROI кампании, %</li>
            <li><strong>ROI Trend</strong> - скорость роста ROI (%/день)</li>
            <li><strong>Days to Breakeven</strong> - расчетное количество дней до ROI = 0</li>
            <li><strong>Projected Date</strong> - прогнозируемая дата выхода в ноль</li>
            <li><strong>R-squared</strong> - качество модели (0.3-1.0, выше = надежнее)</li>
            <li><strong>Confidence</strong> - уровень уверенности: high (R²>0.7), medium (R²>0.4), low (R²<0.4)</li>
        `,

        paramTranslations: {
            min_spend: 'Минимальный расход',
            days_history: 'Дней истории',
            min_trend: 'Минимальный тренд',
            min_r_squared: 'Минимальная точность'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.results) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const forecasts = results.data.results;
            const period = results.data.period || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('current_roi', 'Текущий ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_trend', 'Тренд ROI/день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_to_breakeven', 'Дней до нуля', 'number', sortState.column, sortState.direction)}
                                    <th>Прогноз даты</th>
                                    ${renderSortableHeader('r_squared', 'R²', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('confidence', 'Уверенность', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_of_data', 'Дней данных', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                forecasts.forEach(forecast => {
                    const binomId = forecast.binom_id || forecast.campaign_id;

                    const priorityIcon = forecast.priority === 'high' ? '🔥' :
                                        forecast.priority === 'medium' ? '⚡' : '⏳';

                    const confidenceClass = forecast.confidence === 'high' ? 'text-success' :
                                           forecast.confidence === 'medium' ? 'text-warning' : 'text-muted';

                    const confidenceLabel = forecast.confidence === 'high' ? 'Высокая' :
                                           forecast.confidence === 'medium' ? 'Средняя' : 'Низкая';

                    const projectedDate = new Date(forecast.projected_date).toLocaleDateString('ru-RU');

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(forecast.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(forecast.group)}</small>
                            </td>
                            <td class="text-danger">${formatROI(forecast.current_roi)}</td>
                            <td class="text-success">+${forecast.roi_trend.toFixed(3)}%</td>
                            <td>
                                ${priorityIcon} <strong>${forecast.days_to_breakeven.toFixed(1)}</strong> дн.
                                <br><small class="text-muted">(${forecast.priority_label})</small>
                            </td>
                            <td>${projectedDate}</td>
                            <td>${forecast.r_squared.toFixed(3)}</td>
                            <td class="${confidenceClass}">${confidenceLabel}</td>
                            <td>${formatCurrency(forecast.total_cost)}</td>
                            <td>${forecast.days_of_data}</td>
                            <td>${renderBinomLink(binomId)}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;

                // Info banner в конце
                html += `
                    <div class="info-banner">
                        <strong>Период анализа:</strong> ${period.days_history || 7} дней истории |
                        <strong>Найдено:</strong> ${forecasts.length} кампаний с прогнозом выхода в плюс
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, forecasts, (col, dir) => render(), sortState);
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(ProfitabilityHorizonModule);
    }
})();
