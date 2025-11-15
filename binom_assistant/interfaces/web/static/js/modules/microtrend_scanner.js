/**
 * Модуль: Сканер микро-трендов
 * Анализирует краткосрочные тренды (3-7 дней)
 */
(function() {
    const MicrotrendScannerModule = {
        id: 'microtrend_scanner',

        translations: {
            total_positive: 'Растущих трендов',
            total_negative: 'Падающих трендов',
            total_neutral: 'Стабильных кампаний',
            avg_roi_change_positive: 'Средний рост ROI',
            avg_roi_change_negative: 'Среднее падение ROI'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика за выбранный период (по умолчанию 7 дней)</li>
                <li>Период делится на две равные части для сравнения динамики</li>
                <li>Для каждой половины рассчитываются метрики: ROI, EPC, CR</li>
                <li>Фильтруются кампании с минимальными расходами ($3) и кликами (50)</li>
                <li>Вычисляется процент изменения каждой метрики между половинами</li>
                <li>Тренды классифицируются: растущие (+15%+), падающие (-15%-), стабильные</li>
                <li>Формируются списки растущих и падающих трендов с детализацией изменений</li>
                <li>Создаются алерты для сильных трендов (изменение >30%)</li>
            </ol>
        `,

        metrics: `
            <li><strong>ROI (Return on Investment)</strong> - рентабельность инвестиций ((Revenue - Cost) / Cost * 100), %</li>
            <li><strong>ROI изменение</strong> - разница ROI между второй и первой половиной периода, %</li>
            <li><strong>EPC (Earnings Per Click)</strong> - доход на один клик (Revenue / Clicks), $</li>
            <li><strong>EPC изменение</strong> - процент изменения EPC между половинами периода, %</li>
            <li><strong>CR (Conversion Rate)</strong> - конверсия в лиды (Leads / Clicks * 100), %</li>
            <li><strong>CR изменение</strong> - процент изменения CR между половинами периода, %</li>
            <li><strong>Cost (Расход)</strong> - общие затраты за период, $</li>
            <li><strong>Revenue (Доход)</strong> - общая прибыль за период, $</li>
            <li><strong>Clicks (Клики)</strong> - общее количество кликов за период</li>
            <li><strong>Leads (Лиды)</strong> - общее количество лидов за период</li>
            <li><strong>Период анализа</strong> - количество дней для анализа (по умолчанию 7)</li>
            <li><strong>Минимальный расход</strong> - порог фильтрации ($3 по умолчанию)</li>
            <li><strong>Минимум кликов</strong> - порог фильтрации (50 по умолчанию)</li>
            <li><strong>Значительное изменение</strong> - порог для классификации тренда (15% по умолчанию)</li>
        `,

        paramTranslations: {
            days: 'Период анализа',
            min_spend: 'Минимальный расход',
            min_clicks: 'Минимум кликов',
            significant_change: 'Значительное изменение'
        },

        /**
         * Кастомная отрисовка таблицы для microtrend_scanner
         * Отображает две таблицы: растущие и падающие тренды
         */
        renderTable: function(results, container) {
            const positiveTrends = results.data.positive_trends || [];
            const negativeTrends = results.data.negative_trends || [];

            if (positiveTrends.length === 0 && negativeTrends.length === 0) {
                container.innerHTML = '<p class="text-muted">Нет трендов для отображения</p>';
                return;
            }

            const posSortState = {column: null, direction: 'asc'};
            const negSortState = {column: null, direction: 'asc'};

            const renderPositiveTable = () => {
                if (positiveTrends.length === 0) return '';
                let html = `
                    <div class="trend-section" id="positiveTrendsContainer">
                        <h3 style="color: #10b981; margin-bottom: 1rem;">
                            Растущие тренды (${positiveTrends.length})
                        </h3>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Кампания</th>
                                        ${renderSortableHeader('current_roi', 'ROI', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('roi_change', 'Изменение ROI', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('epc', 'EPC', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('epc_change', 'Δ EPC', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('cr', 'CR', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('cr_change', 'Δ CR', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('total_cost', 'Расход', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('total_revenue', 'Доход', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('total_clicks', 'Клики', 'number', posSortState.column, posSortState.direction)}
                                        ${renderSortableHeader('total_leads', 'Лиды', 'number', posSortState.column, posSortState.direction)}
                                        <th>Binom</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;
                positiveTrends.forEach(trend => {
                    html += `
                        <tr>
                            <td><strong>[${trend.binom_id}] ${escapeHtml(trend.name)}</strong><br><small class="text-muted">${escapeHtml(trend.group)}</small></td>
                            <td class="text-success"><strong>${trend.current_roi.toFixed(2)}%</strong></td>
                            <td class="text-success"><strong>+${trend.roi_change.toFixed(2)}%</strong></td>
                            <td>$${trend.epc.toFixed(3)}</td>
                            <td class="${trend.epc_change >= 0 ? 'text-success' : 'text-danger'}">${trend.epc_change > 0 ? '+' : ''}${trend.epc_change.toFixed(1)}%</td>
                            <td>${trend.cr.toFixed(2)}%</td>
                            <td class="${trend.cr_change >= 0 ? 'text-success' : 'text-danger'}">${trend.cr_change > 0 ? '+' : ''}${trend.cr_change.toFixed(2)}%</td>
                            <td>$${trend.total_cost.toFixed(2)}</td>
                            <td>$${trend.total_revenue.toFixed(2)}</td>
                            <td>${trend.total_clicks}</td>
                            <td>${trend.total_leads}</td>
                            <td>${renderBinomLink(trend.binom_id)}</td>
                        </tr>
                    `;
                });
                html += `</tbody></table></div></div>`;
                return html;
            };

            const renderNegativeTable = () => {
                if (negativeTrends.length === 0) return '';
                let html = `
                    <div class="trend-section" style="margin-top: 2rem;" id="negativeTrendsContainer">
                        <h3 style="color: #ef4444; margin-bottom: 1rem;">
                            Падающие тренды (${negativeTrends.length})
                        </h3>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Кампания</th>
                                        ${renderSortableHeader('current_roi', 'ROI', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('roi_change', 'Изменение ROI', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('epc', 'EPC', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('epc_change', 'Δ EPC', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('cr', 'CR', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('cr_change', 'Δ CR', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('total_cost', 'Расход', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('total_revenue', 'Доход', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('total_clicks', 'Клики', 'number', negSortState.column, negSortState.direction)}
                                        ${renderSortableHeader('total_leads', 'Лиды', 'number', negSortState.column, negSortState.direction)}
                                        <th>Binom</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;
                negativeTrends.forEach(trend => {
                    html += `
                        <tr>
                            <td><strong>[${trend.binom_id}] ${escapeHtml(trend.name)}</strong><br><small class="text-muted">${escapeHtml(trend.group)}</small></td>
                            <td class="${trend.current_roi < 0 ? 'text-danger' : 'text-warning'}">${trend.current_roi.toFixed(2)}%</td>
                            <td class="text-danger"><strong>${trend.roi_change.toFixed(2)}%</strong></td>
                            <td>$${trend.epc.toFixed(3)}</td>
                            <td class="${trend.epc_change >= 0 ? 'text-success' : 'text-danger'}">${trend.epc_change > 0 ? '+' : ''}${trend.epc_change.toFixed(1)}%</td>
                            <td>${trend.cr.toFixed(2)}%</td>
                            <td class="${trend.cr_change >= 0 ? 'text-success' : 'text-danger'}">${trend.cr_change > 0 ? '+' : ''}${trend.cr_change.toFixed(2)}%</td>
                            <td>$${trend.total_cost.toFixed(2)}</td>
                            <td>$${trend.total_revenue.toFixed(2)}</td>
                            <td>${trend.total_clicks}</td>
                            <td>${trend.total_leads}</td>
                            <td>${renderBinomLink(trend.binom_id)}</td>
                        </tr>
                    `;
                });
                html += `</tbody></table></div></div>`;
                return html;
            };

            const render = () => {
                container.innerHTML = renderPositiveTable() + renderNegativeTable();

                // Подключаем сортировку для положительных трендов
                if (positiveTrends.length > 0) {
                    const posContainer = container.querySelector('#positiveTrendsContainer .table-container');
                    if (posContainer) {
                        attachTableSortHandlers(posContainer, positiveTrends, (col, dir) => render(), posSortState);
                    }
                }

                // Подключаем сортировку для отрицательных трендов
                if (negativeTrends.length > 0) {
                    const negContainer = container.querySelector('#negativeTrendsContainer .table-container');
                    if (negContainer) {
                        attachTableSortHandlers(negContainer, negativeTrends, (col, dir) => render(), negSortState);
                    }
                }
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(MicrotrendScannerModule);
    }
})();
