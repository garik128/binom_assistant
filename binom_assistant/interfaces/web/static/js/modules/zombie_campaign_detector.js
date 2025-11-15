/**
 * Модуль: Мертвые кампании (Зомби-кампании)
 * Находит кампании с тратами но без лидов
 */
(function() {
    const ZombieCampaignDetectorModule = {
        id: 'zombie_campaign_detector',

        translations: {
            total_problems: 'Зомби-кампаний',
            critical_count: 'Критично (0 лидов)',
            high_count: 'Высокий (низкий CR)',
            total_checked: 'Проверено кампаний',
            total_wasted: 'Потрачено впустую ($)'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по кампаниям за период</li>
                <li>Расчет средних дневных метрик:
                    <ul>
                        <li>avg_daily_cost = total_cost / days_with_data</li>
                        <li>avg_daily_clicks = total_clicks / days_with_data</li>
                    </ul>
                </li>
                <li>Фильтрация: avg_daily_cost >= min_spend AND avg_daily_clicks >= min_clicks</li>
                <li>Расчет CR: (total_leads / total_clicks) * 100</li>
                <li>Определение зомби-кампаний:
                    <ul>
                        <li><strong>Critical</strong>: leads = 0 (совсем нет лидов)</li>
                        <li><strong>High</strong>: CR < min_cr (очень низкий CR)</li>
                    </ul>
                </li>
                <li>Подсчет дней с проблемой (дни с активностью но без лидов или с низким CR)</li>
                <li>Фильтрация: days_with_problem >= min_days</li>
                <li>wasted_budget = total_cost (весь расход считается потраченным впустую)</li>
                <li>Сортировка по wasted_budget DESC (больше потрачено впустую - выше)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Total Cost</strong> - общий расход за период ($)</li>
            <li><strong>Avg Daily Cost</strong> - средний расход в день ($)</li>
            <li><strong>Total Clicks</strong> - всего кликов за период</li>
            <li><strong>Avg Daily Clicks</strong> - среднее количество кликов в день</li>
            <li><strong>Total Leads</strong> - всего лидов за период</li>
            <li><strong>Conversion Rate</strong> - конверсия лидов (%)</li>
            <li><strong>Days with Problem</strong> - количество дней с проблемой</li>
            <li><strong>Wasted Budget</strong> - потраченный впустую бюджет ($)</li>
            <li><strong>Severity</strong> - критичность (critical/high)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_spend: 'Минимальный расход в день ($)',
            min_clicks: 'Минимум кликов в день',
            min_cr: 'Минимальный CR (%)',
            min_days: 'Минимум дней с проблемой'
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
                                    ${renderSortableHeader('avg_daily_cost', 'Расход в день ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_daily_clicks', 'Клики в день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_leads', 'Всего лидов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('conversion_rate', 'CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_with_problem', 'Дней с проблемой', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('wasted_budget', 'Потрачено впустую ($)', 'number', sortState.column, sortState.direction)}
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
                    let crClass = 'text-danger';
                    if (campaign.conversion_rate > 0.5) {
                        crClass = 'text-warning';
                    }

                    // Цвет для wasted_budget
                    let wastedClass = 'text-danger';
                    if (campaign.wasted_budget < 10) {
                        wastedClass = 'text-warning';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <strong>$${campaign.avg_daily_cost.toFixed(2)}</strong>
                                <br><small class="text-muted">всего: $${campaign.total_cost.toFixed(2)}</small>
                            </td>
                            <td>
                                <strong>${campaign.avg_daily_clicks.toFixed(0)}</strong>
                                <br><small class="text-muted">всего: ${formatNumber(campaign.total_clicks)}</small>
                            </td>
                            <td>
                                ${campaign.total_leads === 0 ?
                                    '<span class="text-danger"><strong>0</strong></span>' :
                                    `<span class="text-warning">${formatNumber(campaign.total_leads)}</span>`
                                }
                            </td>
                            <td>
                                <span class="${crClass}">
                                    ${campaign.conversion_rate.toFixed(2)}%
                                </span>
                            </td>
                            <td>
                                <strong>${campaign.days_with_problem}</strong> ${campaign.days_with_problem === 1 ? 'день' : 'дней'}
                            </td>
                            <td>
                                <span class="${wastedClass}">
                                    <strong>$${campaign.wasted_budget.toFixed(2)}</strong>
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
                        <strong>Мин. расход:</strong> $${params.min_spend || 5}/день |
                        <strong>Мин. клики:</strong> ${params.min_clicks || 20}/день |
                        <strong>Мин. CR:</strong> ${params.min_cr || 0.1}% |
                        <strong>Мин. дней:</strong> ${params.min_days || 2}
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
        ModuleRegistry.register(ZombieCampaignDetectorModule);
    }
})();
