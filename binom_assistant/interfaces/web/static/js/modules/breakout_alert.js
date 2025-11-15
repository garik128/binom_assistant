/**
 * Модуль: Прорыв (Breakout Alert)
 * Находит кампании с прорывом после периода стагнации
 */
(function() {
    const BreakoutAlertModule = {
        id: 'breakout_alert',

        translations: {
            total_breakouts: 'Прорывов обнаружено',
            avg_roi_growth: 'Средний рост ROI (%)',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за (stagnation_days + recent_days) дней</li>
                <li>Разделение данных на два периода:
                    <ul>
                        <li><strong>Stagnation</strong>: период стагнации stagnation_days дней (по умолчанию 10)</li>
                        <li><strong>Recent</strong>: период прорыва recent_days дней (по умолчанию 3)</li>
                    </ul>
                </li>
                <li>Анализ стагнации:
                    <ul>
                        <li>Расчет дневных ROI за период стагнации</li>
                        <li>stagnation_avg_roi = mean(daily_roi_values)</li>
                        <li>stagnation_std_roi = std_dev(daily_roi_values)</li>
                        <li>stagnation_cv = std_roi / avg_roi</li>
                    </ul>
                </li>
                <li>Фильтрация стагнации:
                    <ul>
                        <li>stagnation_cv <= stagnation_threshold / 100 (по умолчанию 0.2)</li>
                        <li>Низкий CV означает стабильные показатели</li>
                    </ul>
                </li>
                <li>Расчет метрик для recent периода:
                    <ul>
                        <li>recent_roi = ((revenue - cost) / cost) * 100</li>
                        <li>recent_cr = (leads / clicks) * 100</li>
                    </ul>
                </li>
                <li>Расчет роста:
                    <ul>
                        <li>roi_growth = ((recent_roi - stagnation_avg_roi) / abs(stagnation_avg_roi)) * 100</li>
                        <li>traffic_change = ((recent_clicks - stagnation_clicks) / stagnation_clicks) * 100</li>
                    </ul>
                </li>
                <li>Фильтрация прорыва:
                    <ul>
                        <li>roi_growth >= breakout_threshold (по умолчанию 30%)</li>
                        <li>abs(traffic_change) <= traffic_change_limit (по умолчанию 50%)</li>
                        <li>recent_clicks >= min_clicks (по умолчанию 50)</li>
                        <li>recent_cr > stagnation_cr (подтверждение CR)</li>
                    </ul>
                </li>
                <li>Сортировка: по roi_growth_percent DESC</li>
            </ol>
        `,

        metrics: `
            <li><strong>Stagnation Avg ROI</strong> - средний ROI в период стагнации (%)</li>
            <li><strong>Stagnation Std ROI</strong> - стандартное отклонение ROI в период стагнации</li>
            <li><strong>Recent ROI</strong> - ROI после прорыва (%)</li>
            <li><strong>ROI Growth</strong> - процент роста ROI</li>
            <li><strong>Stagnation Clicks</strong> - клики в период стагнации</li>
            <li><strong>Recent Clicks</strong> - клики в период прорыва</li>
            <li><strong>Traffic Change</strong> - изменение трафика между периодами (%)</li>
            <li><strong>Stagnation CR</strong> - CR в период стагнации (%)</li>
            <li><strong>Recent CR</strong> - CR в период прорыва (%)</li>
            <li><strong>CR Confirmed</strong> - подтверждение роста CR (true/false)</li>
        `,

        paramTranslations: {
            stagnation_days: 'Период стагнации (дней)',
            stagnation_threshold: 'Диапазон стагнации ROI (±%)',
            recent_days: 'Период прорыва (дней)',
            breakout_threshold: 'Порог прорыва ROI (%)',
            traffic_change_limit: 'Максимальное изменение трафика (%)',
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
                                    ${renderSortableHeader('stagnation_avg_roi', 'ROI до прорыва (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('recent_roi', 'ROI после прорыва (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_growth_percent', 'Рост ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('traffic_change_percent', 'Изменение трафика (%)', 'number', sortState.column, sortState.direction)}
                                    <th>CR до/после</th>
                                    <th>Подтверждение CR</th>
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет для роста ROI
                    let roiGrowthClass = 'text-success';
                    let roiGrowthLabel = 'умеренный';
                    if (campaign.roi_growth_percent > 100) {
                        roiGrowthClass = 'text-success';
                        roiGrowthLabel = 'сильный';
                    } else if (campaign.roi_growth_percent >= 50) {
                        roiGrowthClass = 'text-info';
                        roiGrowthLabel = 'средний';
                    } else {
                        roiGrowthClass = 'text-warning';
                        roiGrowthLabel = 'умеренный';
                    }

                    // Цвет для изменения трафика
                    let trafficChangeClass = 'text-success';
                    if (Math.abs(campaign.traffic_change_percent) > 30) {
                        trafficChangeClass = 'text-warning';
                    } else if (Math.abs(campaign.traffic_change_percent) > 20) {
                        trafficChangeClass = 'text-info';
                    }

                    // Иконка для подтверждения CR
                    const crConfirmedIcon = campaign.cr_confirmed
                        ? '<span class="text-success">&#10004;</span>'
                        : '<span class="text-danger">&#10008;</span>';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="text-muted">
                                    ${campaign.stagnation_avg_roi.toFixed(1)}%
                                </span>
                                <br><small class="text-muted">
                                    σ: ${campaign.stagnation_std_roi.toFixed(2)}
                                </small>
                            </td>
                            <td>
                                <span class="text-success">
                                    <strong>${campaign.recent_roi.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                <span class="${roiGrowthClass}">
                                    <strong>+${campaign.roi_growth_percent.toFixed(1)}%</strong>
                                </span>
                                <br><small class="text-muted">${roiGrowthLabel}</small>
                            </td>
                            <td>
                                <span class="${trafficChangeClass}">
                                    ${campaign.traffic_change_percent >= 0 ? '+' : ''}${campaign.traffic_change_percent.toFixed(1)}%
                                </span>
                                <br><small class="text-muted">
                                    ${formatNumber(campaign.stagnation_clicks)} &rarr; ${formatNumber(campaign.recent_clicks)}
                                </small>
                            </td>
                            <td>
                                ${campaign.stagnation_cr.toFixed(2)}% &rarr; ${campaign.recent_cr.toFixed(2)}%
                                <br><small class="text-muted">
                                    ${campaign.recent_cr > campaign.stagnation_cr ?
                                        '<span class="text-success">рост</span>' :
                                        '<span class="text-danger">падение</span>'}
                                </small>
                            </td>
                            <td style="text-align: center; font-size: 1.5em;">
                                ${crConfirmedIcon}
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
                        <strong>Период стагнации:</strong> ${period.stagnation_days || 10} дней |
                        <strong>Период прорыва:</strong> ${period.recent_days || 3} дней |
                        <strong>Порог прорыва ROI:</strong> ${params.breakout_threshold || 30}% |
                        <strong>Макс. изменение трафика:</strong> ${params.traffic_change_limit || 50}% |
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
        ModuleRegistry.register(BreakoutAlertModule);
    }
})();
