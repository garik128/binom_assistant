/**
 * Модуль: Выгорание источника
 * Определяет выгорание источников трафика
 */
(function() {
    const SourceFatigueDetectorModule = {
        id: 'source_fatigue_detector',

        translations: {
            total_problems: 'Кампаний с выгоранием',
            critical_count: 'Критично (CPC >50%)',
            high_count: 'Высокий (CPC >40%)',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Определение периодов анализа:
                    <ul>
                        <li>Текущий период: последние <code>days</code> дней (включая сегодня)</li>
                        <li>Предыдущий период: предыдущие <code>days</code> дней</li>
                    </ul>
                </li>
                <li>Загрузка данных по кампаниям за оба периода</li>
                <li>Фильтрация: <code>current_clicks >= min_clicks</code> AND <code>previous_clicks >= min_clicks</code></li>
                <li>Расчет метрик для обоих периодов:
                    <ul>
                        <li><strong>CPC</strong> = cost / clicks</li>
                        <li><strong>CR</strong> = (leads / clicks) * 100</li>
                    </ul>
                </li>
                <li>Расчет изменений:
                    <ul>
                        <li><strong>CPC growth %</strong> = ((current_cpc - previous_cpc) / previous_cpc) * 100</li>
                        <li><strong>CR drop %</strong> = ((previous_cr - current_cr) / previous_cr) * 100</li>
                        <li><strong>Traffic change %</strong> = ((current_clicks - previous_clicks) / previous_clicks) * 100</li>
                    </ul>
                </li>
                <li>Определение выгорания:
                    <ul>
                        <li>Фильтр: <code>cpc_growth >= cpc_growth_threshold</code> AND <code>cr_drop > 0</code></li>
                    </ul>
                </li>
                <li>Определение критичности:
                    <ul>
                        <li><strong>Critical</strong>: CPC growth > 50% AND CR падает</li>
                        <li><strong>High</strong>: CPC growth > cpc_growth_threshold AND CR падает</li>
                    </ul>
                </li>
                <li>Сортировка по cpc_growth_percent DESC (больший рост CPC - выше)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Current CPC</strong> - текущий CPC ($)</li>
            <li><strong>Previous CPC</strong> - предыдущий CPC ($)</li>
            <li><strong>CPC Growth %</strong> - рост CPC в процентах</li>
            <li><strong>Current CR</strong> - текущий CR (%)</li>
            <li><strong>Previous CR</strong> - предыдущий CR (%)</li>
            <li><strong>CR Drop %</strong> - падение CR в процентах</li>
            <li><strong>Current Clicks</strong> - клики в текущем периоде</li>
            <li><strong>Previous Clicks</strong> - клики в предыдущем периоде</li>
            <li><strong>Traffic Change %</strong> - изменение трафика в процентах</li>
            <li><strong>Severity</strong> - критичность (critical/high)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            cpc_growth_threshold: 'Порог роста CPC (%)',
            cr_drop_threshold: 'Порог падения CR (%)',
            min_clicks: 'Минимум кликов за период'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.campaigns;
            const periods = results.data.periods || {};
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
                                    ${renderSortableHeader('current_cpc', 'Текущий CPC ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_cpc', 'Предыдущий CPC ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cpc_growth_percent', 'Рост CPC (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_cr', 'Текущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_cr', 'Предыдущий CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr_drop_percent', 'Падение CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('traffic_change_percent', 'Изменение трафика (%)', 'number', sortState.column, sortState.direction)}
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

                    // Цвет для CPC growth
                    let cpcGrowthClass = 'text-danger';
                    if (campaign.cpc_growth_percent < 50) {
                        cpcGrowthClass = 'text-warning';
                    }

                    // Цвет для CR drop
                    let crDropClass = 'text-danger';
                    if (campaign.cr_drop_percent < 30) {
                        crDropClass = 'text-warning';
                    }

                    // Цвет для traffic change
                    let trafficChangeClass = 'text-muted';
                    if (campaign.traffic_change_percent > 10) {
                        trafficChangeClass = 'text-success';
                    } else if (campaign.traffic_change_percent < -10) {
                        trafficChangeClass = 'text-danger';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <strong class="text-danger">$${campaign.current_cpc.toFixed(3)}</strong>
                            </td>
                            <td>
                                <span class="text-muted">$${campaign.previous_cpc.toFixed(3)}</span>
                            </td>
                            <td>
                                <span class="${cpcGrowthClass}">
                                    <strong>+${campaign.cpc_growth_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                <span class="text-warning">${campaign.current_cr.toFixed(2)}%</span>
                            </td>
                            <td>
                                <span class="text-muted">${campaign.previous_cr.toFixed(2)}%</span>
                            </td>
                            <td>
                                <span class="${crDropClass}">
                                    <strong>-${campaign.cr_drop_percent.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                <span class="${trafficChangeClass}">
                                    ${campaign.traffic_change_percent > 0 ? '+' : ''}${campaign.traffic_change_percent.toFixed(1)}%
                                </span>
                                <br>
                                <small class="text-muted">
                                    ${formatNumber(campaign.previous_clicks)} → ${formatNumber(campaign.current_clicks)}
                                </small>
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
                        <strong>Период:</strong> ${periods.days || 7} дней |
                        <strong>Текущий:</strong> ${periods.current?.date_from || ''} - ${periods.current?.date_to || ''} |
                        <strong>Предыдущий:</strong> ${periods.previous?.date_from || ''} - ${periods.previous?.date_to || ''} |
                        <strong>Порог CPC:</strong> ${params.cpc_growth_threshold || 40}% |
                        <strong>Мин. клики:</strong> ${params.min_clicks || 100}
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
        ModuleRegistry.register(SourceFatigueDetectorModule);
    }
})();
