/**
 * Модуль: Крах качества трафика
 * Находит кампании с резким падением конверсии
 */
(function() {
    const TrafficQualityCrashModule = {
        id: 'traffic_quality_crash',

        translations: {
            total_affected_clicks: 'Затронуто кликов'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика за 14 дней (7 текущих + 7 предыдущих для сравнения)</li>
                <li>Для каждой кампании вычисляется CR за текущий и предыдущий периоды</li>
                <li>Проверяется стабильность объема трафика (разница кликов должна быть ±20%)</li>
                <li>Фильтруются кампании с минимум 500 кликами за текущий период</li>
                <li>Вычисляется процент падения CR относительно предыдущего периода</li>
                <li>Рассчитывается среднее значение и стандартное отклонение (σ) для дневных CR</li>
                <li>Проверяется отклонение текущего CR от среднего (должно быть > 2σ)</li>
                <li>Выявляются кампании с падением CR > 40% при всех выполненных условиях</li>
                <li>Определяется критичность на основе степени падения (>70% - критично, >50% - высокая)</li>
            </ol>
        `,

        metrics: `
            <li><strong>CR (Conversion Rate)</strong> - конверсия в лиды (Leads / Clicks * 100), %</li>
            <li><strong>Текущий CR</strong> - средний CR за последние 7 дней, %</li>
            <li><strong>Предыдущий CR</strong> - средний CR за предыдущие 7 дней, %</li>
            <li><strong>Падение CR</strong> - процент падения относительно предыдущего периода, %</li>
            <li><strong>Среднее CR (μ)</strong> - среднее значение дневных CR за весь период, %</li>
            <li><strong>Стандартное отклонение (σ)</strong> - мера разброса дневных CR</li>
            <li><strong>Сигма отклонение</strong> - отклонение текущего CR от среднего в единицах σ</li>
            <li><strong>Стабильность трафика</strong> - изменение объема кликов между периодами, %</li>
            <li><strong>Минимум кликов</strong> - минимальное количество кликов для анализа (по умолчанию 500)</li>
            <li><strong>Порог падения CR</strong> - минимальный процент падения для срабатывания (по умолчанию 40%)</li>
            <li><strong>Порог сигмы</strong> - минимальное отклонение в σ для срабатывания (по умолчанию 2)</li>
        `,

        paramTranslations: {
            cr_drop_threshold: 'Порог падения CR',
            traffic_stability: 'Стабильность трафика',
            min_clicks: 'Минимум кликов',
            sigma_threshold: 'Порог сигмы',
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
                let html = '<div class="table-container"><table><thead><tr><th>Кампания</th>';
                html += renderSortableHeader('previous_cr', 'CR было', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('current_cr', 'CR стало', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('cr_drop_percent', 'Падение CR', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('previous_clicks', 'Кликов было', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('current_clicks', 'Кликов стало', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('avg_roi', 'ROI', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction);
                html += '<th>Binom</th></tr></thead><tbody>';
                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;
                    html += `<tr><td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>`;
                    html += `<td>${campaign.previous_cr.toFixed(2)}%</td>`;
                    html += `<td class="${campaign.current_cr < campaign.previous_cr ? 'text-danger' : ''}">${campaign.current_cr.toFixed(2)}%</td>`;
                    html += `<td class="text-danger"><strong>-${campaign.cr_drop_percent.toFixed(2)}%</strong></td>`;
                    html += `<td>${campaign.previous_clicks}</td>`;
                    html += `<td>${campaign.current_clicks}</td>`;
                    html += `<td>${formatROI(campaign.avg_roi)}</td>`;
                    html += `<td>${formatSeverity(campaign.severity)}</td>`;
                    html += `<td>${renderBinomLink(binomId)}</td></tr>`;
                });
                html += '</tbody></table></div>';
                container.innerHTML = html;
                attachTableSortHandlers(container, campaigns, (col, dir) => render(), sortState);
            };
            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(TrafficQualityCrashModule);
    }
})();
