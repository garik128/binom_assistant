/**
 * Модуль: Неожиданный лидер (Sudden Winner Detector)
 * Обнаруживает кампании с внезапным ростом эффективности
 */
(function() {
    const SuddenWinnerDetectorModule = {
        id: 'sudden_winner_detector',

        translations: {
            total_winners: 'Внезапных победителей',
            roi_surge: 'Рост ROI',
            cr_surge: 'Рост CR',
            both: 'Рост ROI и CR',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за (recent_days + comparison_days) дней</li>
                <li>Разделение данных на два периода:
                    <ul>
                        <li><strong>Previous</strong>: предыдущие comparison_days дней (по умолчанию 7)</li>
                        <li><strong>Recent</strong>: последние recent_days дней (по умолчанию 3)</li>
                    </ul>
                </li>
                <li>Расчет метрик для каждого периода:
                    <ul>
                        <li>ROI = ((revenue - cost) / cost) * 100</li>
                        <li>CR = (leads / clicks) * 100</li>
                    </ul>
                </li>
                <li>Расчет роста метрик:
                    <ul>
                        <li>roi_growth = ((recent_roi - previous_roi) / abs(previous_roi)) * 100</li>
                        <li>cr_growth = ((recent_cr - previous_cr) / previous_cr) * 100</li>
                    </ul>
                </li>
                <li>Фильтрация:
                    <ul>
                        <li>recent_clicks >= min_clicks (по умолчанию 50)</li>
                        <li>roi_growth >= roi_growth_threshold (по умолчанию 50%) ИЛИ cr_growth >= cr_growth_threshold (по умолчанию 100%)</li>
                    </ul>
                </li>
                <li>Определение win_type:
                    <ul>
                        <li><strong>both</strong>: выполнены оба условия (ROI и CR)</li>
                        <li><strong>roi_surge</strong>: только ROI рост</li>
                        <li><strong>cr_surge</strong>: только CR рост</li>
                    </ul>
                </li>
                <li>Сортировка: сначала both, потом roi_surge, потом cr_surge. Внутри по roi_growth DESC</li>
            </ol>
        `,

        metrics: `
            <li><strong>Recent ROI</strong> - ROI в текущем периоде (%)</li>
            <li><strong>Previous ROI</strong> - ROI в предыдущем периоде (%)</li>
            <li><strong>ROI Growth</strong> - процент роста ROI</li>
            <li><strong>Recent CR</strong> - CR в текущем периоде (%)</li>
            <li><strong>Previous CR</strong> - CR в предыдущем периоде (%)</li>
            <li><strong>CR Growth</strong> - процент роста CR</li>
            <li><strong>Recent Clicks</strong> - клики в текущем периоде</li>
            <li><strong>Win Type</strong> - тип роста (both/roi_surge/cr_surge)</li>
        `,

        paramTranslations: {
            recent_days: 'Период текущей активности (дней)',
            comparison_days: 'Период для сравнения (дней)',
            roi_growth_threshold: 'Порог роста ROI (%)',
            cr_growth_threshold: 'Порог роста CR (%)',
            min_clicks: 'Минимум кликов'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.campaigns;
            const period = results.data.period || {};
            const params = results.data.params || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('recent_roi', 'Текущий ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_roi', 'Предыдущий ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_growth_percent', 'Рост ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('recent_cr', 'Текущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_cr', 'Предыдущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr_growth_percent', 'Рост CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('recent_clicks', 'Текущие клики', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('win_type', 'Тип роста', 'text', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет win_type badge
                    let winTypeClass = 'badge-secondary';
                    let winTypeLabel = 'Неизвестно';
                    if (campaign.win_type === 'both') {
                        winTypeClass = 'badge-success';
                        winTypeLabel = 'ROI + CR';
                    } else if (campaign.win_type === 'roi_surge') {
                        winTypeClass = 'badge-info';
                        winTypeLabel = 'Только ROI';
                    } else if (campaign.win_type === 'cr_surge') {
                        winTypeClass = 'badge-warning';
                        winTypeLabel = 'Только CR';
                    }

                    // Цвет для роста ROI
                    let roiGrowthClass = 'text-success';
                    if (campaign.roi_growth_percent < 100) {
                        roiGrowthClass = 'text-info';
                    }

                    // Цвет для роста CR
                    let crGrowthClass = 'text-success';
                    if (campaign.cr_growth_percent < 150) {
                        crGrowthClass = 'text-info';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="text-success">
                                    <strong>${campaign.recent_roi.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>${campaign.previous_roi.toFixed(1)}%</td>
                            <td>
                                <span class="${roiGrowthClass}">
                                    <strong>+${campaign.roi_growth_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                <span class="text-success">
                                    <strong>${campaign.recent_cr.toFixed(2)}%</strong>
                                </span>
                            </td>
                            <td>${campaign.previous_cr.toFixed(2)}%</td>
                            <td>
                                <span class="${crGrowthClass}">
                                    <strong>+${campaign.cr_growth_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>${formatNumber(campaign.recent_clicks)}</td>
                            <td>
                                <span class="badge ${winTypeClass}">
                                    ${winTypeLabel}
                                </span>
                            </td>
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
                        <strong>Период:</strong> текущие ${period.recent_days || 3} дней vs предыдущие ${period.comparison_days || 7} дней |
                        <strong>Порог роста ROI:</strong> ${params.roi_growth_threshold || 50}% |
                        <strong>Порог роста CR:</strong> ${params.cr_growth_threshold || 100}% |
                        <strong>Мин. кликов:</strong> ${params.min_clicks || 50}
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, campaigns, (col, dir) => render(), sortState);
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SuddenWinnerDetectorModule);
    }
})();
