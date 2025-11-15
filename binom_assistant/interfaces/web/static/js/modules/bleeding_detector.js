/**
 * Модуль: Утекающий бюджет
 * Находит убыточные кампании с ROI < -50%
 */
(function() {
    const BleedingDetectorModule = {
        id: 'bleeding_detector',

        translations: {
            total_losses: 'Общие убытки',
            critical_count: 'Критических',
            high_count: 'Высокой критичности',
            medium_count: 'Средней критичности'
        },

        algorithm: `
            <ol>
                <li>Анализируется статистика кампаний за последние 3 дня</li>
                <li>Фильтруются кампании с расходом более $5</li>
                <li>Вычисляется средний ROI для каждой кампании</li>
                <li>Выявляются кампании с ROI ниже -50% (настраивается)</li>
                <li>Рассчитывается общая сумма убытков</li>
                <li>Формируются рекомендации по отключению</li>
            </ol>
        `,

        metrics: `
            <li><strong>ROI (Return on Investment)</strong> - возврат инвестиций, %</li>
            <li><strong>Cost (Расход)</strong> - затраты на рекламу, $</li>
            <li><strong>Revenue (Доход)</strong> - полученная прибыль, $</li>
            <li><strong>Profit (Прибыль)</strong> - чистая прибыль (Revenue - Cost), $</li>
            <li><strong>Период анализа</strong> - последние 3 дня</li>
        `,

        paramTranslations: {
            roi_threshold: 'Порог ROI',
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
                                    ${renderSortableHeader('avg_roi', 'ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('loss', 'Убыток', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_clicks', 'Клики', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_leads', 'Лиды', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const profit = campaign.total_revenue - campaign.total_cost;
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td>${formatROI(campaign.avg_roi)}</td>
                            <td class="text-danger">$${campaign.loss.toFixed(2)}</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
                            <td>${formatProfit(profit)}</td>
                            <td>${campaign.total_clicks}</td>
                            <td>${campaign.total_leads}</td>
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
        ModuleRegistry.register(BleedingDetectorModule);
    }
})();
