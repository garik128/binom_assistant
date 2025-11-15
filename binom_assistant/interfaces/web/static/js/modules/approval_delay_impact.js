/**
 * Модуль: Задержка апрувов
 * Оценивает влияние задержек апрувов на кэшфлоу
 */
(function() {
    const ApprovalDelayImpactModule = {
        id: 'approval_delay_impact',

        translations: {
            total_problems: 'Проблемных кампаний',
            critical_count: 'Критично (>7 дней)',
            high_count: 'Высокий (>3 дней)',
            total_checked: 'Проверено кампаний',
            avg_delay_overall: 'Средняя задержка (дней)'
        },

        algorithm: `
            <ol>
                <li>Фильтрация: только CPA кампании (a_leads > 0)</li>
                <li>Загрузка данных по лидам (total, approved, pending, rejected) за период</li>
                <li>Расчет pending лидов: pending_leads = h_leads (холд лиды)</li>
                <li>Расчет approval rate: (a_leads / (a_leads + r_leads)) * 100</li>
                <li>Примерная оценка задержки апрувов:
                    <ul>
                        <li>По pending лидам: (pending_leads / total_leads) * days * 0.7</li>
                        <li>По approval rate: (100 - approval_rate) / 100 * days * 0.5</li>
                        <li>avg_delay_days = max из двух оценок</li>
                    </ul>
                </li>
                <li>Расчет замороженных средств:
                    <ul>
                        <li>frozen_funds = cost * (pending_leads / total_leads)</li>
                        <li>frozen_percent = (frozen_funds / total_cost) * 100</li>
                    </ul>
                </li>
                <li>Фильтрация: total_approvals >= min_approvals AND avg_delay >= delay_threshold</li>
                <li>Severity:
                    <ul>
                        <li><strong>critical</strong>: задержка >= 7 дней</li>
                        <li><strong>high</strong>: задержка >= delay_threshold</li>
                    </ul>
                </li>
                <li>Сортировка по avg_delay_days DESC (самая большая задержка сначала)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Avg Delay Days</strong> - примерная средняя задержка апрува (дней)</li>
            <li><strong>Frozen Funds</strong> - замороженные средства ($) в pending лидах</li>
            <li><strong>Frozen %</strong> - процент замороженных средств от общего расхода</li>
            <li><strong>Total Approvals</strong> - всего апрувов за период</li>
            <li><strong>Pending Leads</strong> - количество лидов в холде (ожидают апрува)</li>
            <li><strong>Approval Rate</strong> - процент апрувов от обработанных лидов</li>
            <li><strong>Severity</strong> - критичность (critical/high)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_approvals: 'Минимум апрувов',
            delay_threshold: 'Порог задержки (дней)'
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
                                    ${renderSortableHeader('avg_delay_days', 'Средняя задержка (дней)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('frozen_funds', 'Замороженные средства ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('frozen_percent', 'Замороженный % от расхода', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_approvals', 'Всего апрувов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('pending_leads', 'Pending лидов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('approval_rate', 'Approval Rate (%)', 'number', sortState.column, sortState.direction)}
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

                    // Цвет для задержки
                    let delayClass = 'text-warning';
                    if (campaign.avg_delay_days >= 7) {
                        delayClass = 'text-danger';
                    }

                    // Цвет для frozen_percent
                    let frozenClass = 'text-muted';
                    if (campaign.frozen_percent >= 50) {
                        frozenClass = 'text-danger';
                    } else if (campaign.frozen_percent >= 30) {
                        frozenClass = 'text-warning';
                    }

                    // Цвет для approval_rate
                    let approvalClass = 'text-success';
                    if (campaign.approval_rate < 50) {
                        approvalClass = 'text-danger';
                    } else if (campaign.approval_rate < 70) {
                        approvalClass = 'text-warning';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="${delayClass}">
                                    <strong>${campaign.avg_delay_days.toFixed(1)} дней</strong>
                                </span>
                            </td>
                            <td>
                                <strong>$${campaign.frozen_funds.toFixed(2)}</strong>
                                <br><small class="text-muted">из $${campaign.total_cost.toFixed(2)}</small>
                            </td>
                            <td>
                                <span class="${frozenClass}">
                                    <strong>${campaign.frozen_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>${formatNumber(campaign.total_approvals)}</td>
                            <td>
                                ${campaign.pending_leads > 0 ?
                                    `<span class="text-warning">${formatNumber(campaign.pending_leads)}</span>` :
                                    formatNumber(campaign.pending_leads)
                                }
                            </td>
                            <td>
                                <span class="${approvalClass}">
                                    ${campaign.approval_rate.toFixed(1)}%
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
                        <strong>Период:</strong> ${period.days || 14} дней |
                        <strong>Мин. апрувов:</strong> ${params.min_approvals || 10} |
                        <strong>Порог задержки:</strong> ${params.delay_threshold || 3} дней
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
        ModuleRegistry.register(ApprovalDelayImpactModule);
    }
})();
