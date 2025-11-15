/**
 * Модуль: Маржа CPL
 * Следит за margin в CPL кампаниях
 */
(function() {
    const CPLMarginMonitorModule = {
        id: 'cpl_margin_monitor',

        translations: {
            total_problems: 'Проблемных кампаний',
            critical_count: 'Критично (убыток)',
            high_count: 'Высокий (<10%)',
            medium_count: 'Средний (<20%)',
            total_checked: 'Проверено CPL кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за последние 14 дней (2 периода по days дней)</li>
                <li>Фильтрация только CPL кампаний:
                    <ul>
                        <li>a_leads == 0 (нет апрувов - платят сразу за лид)</li>
                        <li>revenue > 0 (есть доход)</li>
                    </ul>
                </li>
                <li>Разделение данных на два периода:
                    <ul>
                        <li><strong>Current</strong>: последние N дней</li>
                        <li><strong>Previous</strong>: предыдущие N дней</li>
                    </ul>
                </li>
                <li>Расчет метрик для текущего периода:
                    <ul>
                        <li>margin = revenue - cost (чистая прибыль)</li>
                        <li>margin_percent = (margin / revenue) * 100</li>
                    </ul>
                </li>
                <li>Расчет margin_previous для предыдущего периода</li>
                <li>Расчет margin_trend = margin_current - margin_previous</li>
                <li>Фильтрация: только кампании с revenue >= min_revenue</li>
                <li>Определение проблемных:
                    <ul>
                        <li>margin < margin_threshold ($) ИЛИ</li>
                        <li>margin_percent < margin_percent_threshold (%)</li>
                    </ul>
                </li>
                <li>Severity:
                    <ul>
                        <li><strong>critical</strong>: margin < 0 (убыток)</li>
                        <li><strong>high</strong>: margin_percent < 10%</li>
                        <li><strong>medium</strong>: margin_percent < 20%</li>
                    </ul>
                </li>
                <li>Сортировка по margin ASC (самая низкая маржа сначала)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Revenue</strong> - доход кампании ($)</li>
            <li><strong>Cost</strong> - расход кампании ($)</li>
            <li><strong>Margin</strong> - чистая прибыль = revenue - cost ($)</li>
            <li><strong>Margin %</strong> - процент маржи = (margin / revenue) * 100</li>
            <li><strong>Previous Margin</strong> - маржа за предыдущий период ($)</li>
            <li><strong>Margin Trend</strong> - изменение маржи = margin_current - margin_previous ($)</li>
            <li><strong>Severity</strong> - критичность (critical/high/medium)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_revenue: 'Минимум revenue ($)',
            margin_threshold: 'Минимум margin ($)',
            margin_percent_threshold: 'Минимум margin (%)'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.problem_campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const problemCampaigns = results.data.problem_campaigns;
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
                                    ${renderSortableHeader('revenue', 'Revenue', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cost', 'Cost', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('margin', 'Margin ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('margin_percent', 'Margin (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_margin', 'Пред. margin', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('margin_trend', 'Тренд margin', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity_label', 'Критичность', 'text', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                problemCampaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет severity badge
                    let severityClass = 'badge-secondary';
                    if (campaign.severity === 'critical') {
                        severityClass = 'badge-danger';
                    } else if (campaign.severity === 'high') {
                        severityClass = 'badge-warning';
                    } else if (campaign.severity === 'medium') {
                        severityClass = 'badge-info';
                    }

                    // Цвет для margin
                    let marginClass = campaign.margin < 0 ? 'text-danger' : 'text-warning';

                    // Стрелка для тренда
                    let trendIcon = '';
                    let trendClass = '';
                    if (campaign.margin_trend > 0) {
                        trendIcon = '↑';
                        trendClass = 'text-success';
                    } else if (campaign.margin_trend < 0) {
                        trendIcon = '↓';
                        trendClass = 'text-danger';
                    } else {
                        trendIcon = '→';
                        trendClass = 'text-muted';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>${formatCurrency(campaign.revenue)}</td>
                            <td>${formatCurrency(campaign.cost)}</td>
                            <td>
                                <span class="${marginClass}">
                                    <strong>${formatCurrency(campaign.margin)}</strong>
                                </span>
                            </td>
                            <td>
                                <span class="${marginClass}">
                                    <strong>${campaign.margin_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>${formatCurrency(campaign.previous_margin)}</td>
                            <td>
                                <span class="${trendClass}">
                                    ${trendIcon} ${formatCurrency(Math.abs(campaign.margin_trend))}
                                </span>
                            </td>
                            <td>
                                <span class="badge ${severityClass}">
                                    ${campaign.severity_label}
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
                        <strong>Период:</strong> ${period.days || 7} дней |
                        <strong>Порог margin:</strong> ${params.margin_threshold || 5}$ или ${params.margin_percent_threshold || 20}% |
                        <strong>Мин. revenue:</strong> ${params.min_revenue || 10}$
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, problemCampaigns, (col, dir) => render(), sortState);
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(CPLMarginMonitorModule);
    }
})();
