/**
 * Модуль: Матрица источник-группа
 * Построение матрицы эффективности источник-группа
 */
(function() {
    const SourceGroupMatrixModule = {
        id: 'source_group_matrix',

        translations: {
            total_cells: 'Всего ячеек матрицы',
            total_campaigns: 'Всего кампаний',
            profitable_cells: 'Прибыльных ячеек',
            unprofitable_cells: 'Убыточных ячеек'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за последние N дней</li>
                <li>Группировка кампаний по источнику (ts_name) и группе (group_name)</li>
                <li>Агрегация метрик для каждой пары источник-группа:
                    <ul>
                        <li>Суммирование кликов, расходов, доходов, лидов</li>
                        <li>Подсчет количества кампаний</li>
                    </ul>
                </li>
                <li>Фильтрация ячеек матрицы:
                    <ul>
                        <li>Общий расход >= min_cell_spend (по умолчанию $10)</li>
                        <li>Количество кампаний >= min_campaigns (по умолчанию 1)</li>
                    </ul>
                </li>
                <li>Расчет метрик для каждой ячейки:
                    <ul>
                        <li>ROI = (revenue - cost) / cost * 100</li>
                        <li>CR = leads / clicks * 100</li>
                        <li>Profit = revenue - cost</li>
                    </ul>
                </li>
                <li>Сортировка ячеек по ROI</li>
                <li>Выделение топ-5 лучших и худших комбинаций</li>
                <li>Цветовое кодирование ячеек по эффективности</li>
            </ol>
        `,

        metrics: `
            <li><strong>Total Cells</strong> - количество ячеек в матрице</li>
            <li><strong>Total Campaigns</strong> - общее количество кампаний</li>
            <li><strong>Profitable Cells</strong> - количество прибыльных ячеек</li>
            <li><strong>Unprofitable Cells</strong> - количество убыточных ячеек</li>
            <li><strong>ROI</strong> - средний ROI ячейки матрицы</li>
            <li><strong>CR</strong> - средний CR ячейки матрицы</li>
            <li><strong>Profit</strong> - прибыль ячейки матрицы</li>
            <li><strong>Campaigns Count</strong> - количество кампаний в ячейке</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cell_spend: 'Минимальный расход для ячейки ($)',
            min_campaigns: 'Минимум кампаний'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.matrix_cells) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const cells = results.data.matrix_cells;
            const best = results.data.best_combinations || [];
            const worst = results.data.worst_combinations || [];
            const period = results.data.period || {};
            const params = results.data.params || {};

            if (cells.length === 0) {
                container.innerHTML = '<p class="text-muted">Ячеек матрицы не найдено. Попробуйте изменить параметры.</p>';
                return;
            }

            let html = '';

            // Топ-5 лучших комбинаций
            if (best.length > 0) {
                html += `
                    <div class="matrix-section" style="margin: 20px 0; padding: 15px; border: 2px solid rgba(75, 192, 192, 0.8); border-radius: 8px; background: #1a1a1a;">
                        <h4>Топ-5 лучших комбинаций источник-группа</h4>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Источник → Группа</th>
                                        <th>Кампаний</th>
                                        <th>Расход</th>
                                        <th>Доход</th>
                                        <th>Прибыль</th>
                                        <th>ROI (%)</th>
                                        <th>CR (%)</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;

                best.forEach(cell => {
                    const profitClass = cell.profit >= 0 ? 'text-success' : 'text-danger';
                    const roiClass = cell.roi >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td><strong>${escapeHtml(cell.source)}</strong> → <strong>${escapeHtml(cell.group)}</strong></td>
                            <td>${cell.campaigns_count}</td>
                            <td>${formatCurrency(cell.total_cost)}</td>
                            <td>${formatCurrency(cell.total_revenue)}</td>
                            <td><span class="${profitClass}">${formatCurrency(cell.profit)}</span></td>
                            <td><span class="${roiClass}">${cell.roi.toFixed(1)}%</span></td>
                            <td>${cell.cr.toFixed(2)}%</td>
                        </tr>
                    `;
                });

                html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            // Топ-5 худших комбинаций
            if (worst.length > 0) {
                html += `
                    <div class="matrix-section" style="margin: 20px 0; padding: 15px; border: 2px solid rgba(255, 99, 132, 0.8); border-radius: 8px; background: #1a1a1a;">
                        <h4>Топ-5 худших комбинаций источник-группа</h4>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Источник → Группа</th>
                                        <th>Кампаний</th>
                                        <th>Расход</th>
                                        <th>Доход</th>
                                        <th>Прибыль</th>
                                        <th>ROI (%)</th>
                                        <th>CR (%)</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;

                worst.forEach(cell => {
                    const profitClass = cell.profit >= 0 ? 'text-success' : 'text-danger';
                    const roiClass = cell.roi >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td><strong>${escapeHtml(cell.source)}</strong> → <strong>${escapeHtml(cell.group)}</strong></td>
                            <td>${cell.campaigns_count}</td>
                            <td>${formatCurrency(cell.total_cost)}</td>
                            <td>${formatCurrency(cell.total_revenue)}</td>
                            <td><span class="${profitClass}">${formatCurrency(cell.profit)}</span></td>
                            <td><span class="${roiClass}">${cell.roi.toFixed(1)}%</span></td>
                            <td>${cell.cr.toFixed(2)}%</td>
                        </tr>
                    `;
                });

                html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            // Полная матрица
            html += `
                <div class="matrix-section" style="margin: 20px 0; padding: 15px; border: 1px solid #444; border-radius: 8px; background: #1a1a1a;">
                    <h4>Полная матрица источник-группа (${cells.length} ячеек)</h4>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Источник → Группа</th>
                                    <th>Кампаний</th>
                                    <th>Клики</th>
                                    <th>Расход</th>
                                    <th>Доход</th>
                                    <th>Прибыль</th>
                                    <th>ROI (%)</th>
                                    <th>CR (%)</th>
                                    <th>Детали</th>
                                </tr>
                            </thead>
                            <tbody>
            `;

            // Сортируем все ячейки по ROI для отображения
            const sortedCells = [...cells].sort((a, b) => b.roi - a.roi);

            sortedCells.forEach((cell, index) => {
                const profitClass = cell.profit >= 0 ? 'text-success' : 'text-danger';
                const roiClass = cell.roi >= 0 ? 'text-success' : 'text-danger';

                // Цвет фона в зависимости от ROI
                let bgColor = '';
                if (cell.roi > 50) {
                    bgColor = 'background: rgba(75, 192, 192, 0.1);';
                } else if (cell.roi < 0) {
                    bgColor = 'background: rgba(255, 99, 132, 0.1);';
                }

                html += `
                    <tr style="${bgColor}">
                        <td><strong>${escapeHtml(cell.source)}</strong> → <strong>${escapeHtml(cell.group)}</strong></td>
                        <td>${cell.campaigns_count}</td>
                        <td>${formatNumber(cell.total_clicks)}</td>
                        <td>${formatCurrency(cell.total_cost)}</td>
                        <td>${formatCurrency(cell.total_revenue)}</td>
                        <td><span class="${profitClass}">${formatCurrency(cell.profit)}</span></td>
                        <td><span class="${roiClass}">${cell.roi.toFixed(1)}%</span></td>
                        <td>${cell.cr.toFixed(2)}%</td>
                        <td>
                            <button class="btn-sm matrix-cell-details-btn" data-cell-id="cell_${index}">Показать</button>
                            <div id="cell_${index}" style="display: none; margin-top: 10px; padding: 10px; background: #2a2a2a; border-radius: 4px;">
                                <strong>Кампании в этой ячейке:</strong>
                                <ul style="margin: 10px 0; padding-left: 20px;">
                `;

                cell.campaign_details.forEach(campaign => {
                    const campRoiClass = campaign.roi >= 0 ? 'text-success' : 'text-danger';
                    html += `
                        <li>
                            ${renderBinomLink(campaign.binom_id)}
                            [${campaign.binom_id}] ${escapeHtml(campaign.name)}:
                            ${formatCurrency(campaign.cost)} → ${formatCurrency(campaign.revenue)}
                            (<span class="${campRoiClass}">${campaign.roi.toFixed(1)}%</span>)
                        </li>
                    `;
                });

                html += `
                                </ul>
                            </div>
                        </td>
                    </tr>
                `;
            });

            html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            // Info banner в конце
            html += `
                <div class="info-banner">
                    <strong>Период:</strong> ${period.days || 7} дней |
                    <strong>Мин. расход ячейки:</strong> ${params.min_cell_spend || 10}$ |
                    <strong>Мин. кампаний:</strong> ${params.min_campaigns || 1}
                </div>
            `;

            container.innerHTML = html;

            // Подключаем обработчики для кнопок деталей ячеек через делегирование
            container.addEventListener('click', function(event) {
                if (event.target.classList.contains('matrix-cell-details-btn')) {
                    const cellId = event.target.getAttribute('data-cell-id');
                    const detailsDiv = document.getElementById(cellId);
                    if (detailsDiv) {
                        detailsDiv.style.display = detailsDiv.style.display === 'none' ? 'block' : 'none';
                        // Меняем текст кнопки
                        event.target.textContent = detailsDiv.style.display === 'none' ? 'Показать' : 'Скрыть';
                    }
                }
            });
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SourceGroupMatrixModule);
    }
})();
