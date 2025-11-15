/**
 * Модуль: Алерт нулевого апрува
 * Находит CPA кампании с нулевым процентом апрувов
 */
(function() {
    const ZeroApprovalAlertModule = {
        id: 'zero_approval_alert',

        translations: {
            total_pending_leads: 'Лидов на холде',
            total_wasted: 'Потеряно'
        },

        algorithm: `
            <ol>
                <li>Анализируется статистика кампаний за последние 7 дней</li>
                <li>Отбираются только CPA кампании (is_cpl_mode = False)</li>
                <li>Фильтруются кампании с минимум 10 лидами и расходом более $10</li>
                <li>Выявляются кампании с нулевым процентом апрувов (a_leads = 0)</li>
                <li>Определяется критичность на основе расхода</li>
                <li>Рассчитывается общая сумма потерь и количество лидов на холде</li>
                <li>Формируются рекомендации по проверке постбэка и качества трафика</li>
            </ol>
        `,

        metrics: `
            <li><strong>Leads (Лиды)</strong> - общее количество сгенерированных лидов</li>
            <li><strong>a_leads (Апрувленые лиды)</strong> - количество одобренных лидов</li>
            <li><strong>h_leads (Лиды на холде)</strong> - лиды в ожидании решения</li>
            <li><strong>r_leads (Отклоненные лиды)</strong> - количество отклоненных лидов</li>
            <li><strong>Cost (Расход)</strong> - затраты на рекламу, $</li>
            <li><strong>Revenue (Доход)</strong> - полученная прибыль, $</li>
            <li><strong>CR (Conversion Rate)</strong> - конверсия в лиды, %</li>
            <li><strong>Cost per Lead (Стоимость лида)</strong> - средняя цена за лид, $</li>
            <li><strong>is_cpl_mode</strong> - флаг типа оплаты (CPL/CPA)</li>
            <li><strong>Период анализа</strong> - последние 7 дней</li>
        `,

        paramTranslations: {
            min_leads: 'Минимум лидов',
            min_spend: 'Минимальный расход',
            days: 'Период анализа'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.campaigns;
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('total_leads', 'Всего лидов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('h_leads', 'На холде', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('r_leads', 'Отклонено', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cost_per_lead', 'CPL', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr', 'CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td>${campaign.total_leads}</td>
                            <td class="text-warning">${campaign.h_leads || 0}</td>
                            <td class="text-danger">${campaign.r_leads || 0}</td>
                            <td>${formatCurrency(campaign.cost_per_lead)}</td>
                            <td>${campaign.cr.toFixed(2)}%</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatROI(campaign.avg_roi)}</td>
                            <td>${formatSeverity(campaign.severity)}</td>
                            <td>${renderBinomLink(binomId)}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
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
        ModuleRegistry.register(ZeroApprovalAlertModule);
    }
})();
