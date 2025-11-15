/**
 * Модуль: Падение конверсии
 * Обнаруживает падение CR кампаний
 */
(function() {
    const ConversionDropAlertModule = {
        id: 'conversion_drop_alert',

        translations: {
            total_problems: 'Проблемных кампаний',
            critical_count: 'Критично (>50%)',
            high_count: 'Высокий (>30%)',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по кликам и лидам за последние (days * 2) дней</li>
                <li>Разделение данных на два периода:
                    <ul>
                        <li><strong>Previous</strong>: дни с -(days*2) по -days (предыдущий период)</li>
                        <li><strong>Current</strong>: дни с -days по сегодня (текущий период)</li>
                    </ul>
                </li>
                <li>Расчет CR для каждого периода: CR = (leads / clicks) * 100</li>
                <li>Фильтрация: только кампании с clicks >= min_clicks в обоих периодах</li>
                <li>Расчет падения CR: cr_drop_percent = ((previous_cr - current_cr) / previous_cr) * 100</li>
                <li>Определение проблемных кампаний:
                    <ul>
                        <li>cr_drop_percent >= drop_threshold</li>
                    </ul>
                </li>
                <li>Severity:
                    <ul>
                        <li><strong>critical</strong>: падение >= 50%</li>
                        <li><strong>high</strong>: падение >= 30%</li>
                    </ul>
                </li>
                <li>Сортировка по cr_drop_percent DESC (самое большое падение сначала)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Current CR</strong> - конверсия в текущем периоде (%)</li>
            <li><strong>Previous CR</strong> - конверсия в предыдущем периоде (%)</li>
            <li><strong>CR Drop %</strong> - процент падения конверсии</li>
            <li><strong>Current Clicks/Leads</strong> - клики и лиды в текущем периоде</li>
            <li><strong>Previous Clicks/Leads</strong> - клики и лиды в предыдущем периоде</li>
            <li><strong>Severity</strong> - критичность (critical/high)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            drop_threshold: 'Порог падения CR (%)',
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
                                    ${renderSortableHeader('current_cr', 'Текущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_cr', 'Предыдущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr_drop_percent', 'Падение (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_clicks', 'Текущие клики', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_leads', 'Текущие лиды', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_clicks', 'Предыдущие клики', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_leads', 'Предыдущие лиды', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity_label', 'Статус', 'text', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет severity badge
                    let severityClass = 'badge-secondary';
                    if (campaign.severity === 'critical') {
                        severityClass = 'badge-danger';
                    } else if (campaign.severity === 'high') {
                        severityClass = 'badge-warning';
                    }

                    // Цвет для CR
                    let crClass = campaign.current_cr < campaign.previous_cr ? 'text-danger' : 'text-success';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="${crClass}">
                                    <strong>${campaign.current_cr.toFixed(2)}%</strong>
                                </span>
                            </td>
                            <td>${campaign.previous_cr.toFixed(2)}%</td>
                            <td>
                                <span class="text-danger">
                                    <strong>${campaign.cr_drop_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>${formatNumber(campaign.current_clicks)}</td>
                            <td>${formatNumber(campaign.current_leads)}</td>
                            <td>${formatNumber(campaign.previous_clicks)}</td>
                            <td>${formatNumber(campaign.previous_leads)}</td>
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
                        <strong>Порог падения:</strong> ${params.drop_threshold || 30}% |
                        <strong>Мин. кликов:</strong> ${params.min_clicks || 100}
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
        ModuleRegistry.register(ConversionDropAlertModule);
    }
})();
