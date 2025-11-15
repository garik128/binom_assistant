/**
 * Модуль: Поиск сливных кампаний
 * Находит кампании с длительными периодами убыточности
 */
(function() {
    const WasteCampaignFinderModule = {
        id: 'waste_campaign_finder',

        translations: {
            avg_bad_streak: 'Средняя длительность слива',
            total_wasted: 'Общие потери'
        },

        algorithm: `
            <ol>
                <li>Анализируется дневная статистика кампаний за период (по умолчанию 14 дней)</li>
                <li>Отбираются кампании со средним расходом более $1/день</li>
                <li>Для каждой кампании проверяется наличие последовательности дней с ROI < -50%</li>
                <li>Проверяется длительность последовательности (не менее 7 дней подряд)</li>
                <li>Проверяется отсутствие признаков восстановления в последние 3 дня</li>
                <li>Рассчитывается средний ROI за плохие дни и общая сумма потерь</li>
                <li>Определяется критичность на основе длительности слива (>10 дней - критично)</li>
                <li>Формируются рекомендации по остановке хронических убыточных кампаний</li>
            </ol>
        `,

        metrics: `
            <li><strong>ROI (Return on Investment)</strong> - возврат инвестиций за период, %</li>
            <li><strong>Дневной ROI</strong> - ROI для каждого дня периода, %</li>
            <li><strong>Последовательные убыточные дни</strong> - количество дней подряд с ROI < -50%</li>
            <li><strong>Средний ROI за плохие дни</strong> - среднее значение ROI за убыточные дни, %</li>
            <li><strong>Cost (Расход)</strong> - общие затраты за период, $</li>
            <li><strong>Revenue (Доход)</strong> - общая прибыль за период, $</li>
            <li><strong>Минимальный дневной расход</strong> - порог фильтрации (по умолчанию $1/день)</li>
            <li><strong>Период анализа</strong> - количество дней для анализа (по умолчанию 14)</li>
            <li><strong>Минимальная последовательность</strong> - минимум дней подряд для срабатывания (по умолчанию 7)</li>
        `,

        paramTranslations: {
            min_daily_spend: 'Минимальный дневной расход',
            consecutive_days: 'Минимум дней подряд',
            analysis_period: 'Период анализа',
            roi_threshold: 'Порог ROI'
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
                html += renderSortableHeader('avg_roi', 'Средний ROI', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('avg_bad_roi', 'Средний "плохой" ROI', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('consecutive_bad_days', 'Дней подряд', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('loss', 'Общий убыток', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction);
                html += renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction);
                html += '<th>Binom</th></tr></thead><tbody>';
                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;
                    const avgBadRoi = parseFloat(campaign.avg_bad_roi) || 0;
                    html += `<tr><td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>`;
                    html += `<td>${formatROI(campaign.avg_roi)}</td>`;
                    html += `<td class="text-danger">${avgBadRoi.toFixed(2)}%</td>`;
                    html += `<td class="text-warning"><strong>${campaign.consecutive_bad_days} дн.</strong></td>`;
                    html += `<td class="text-danger"><strong>${formatCurrency(campaign.loss)}</strong></td>`;
                    html += `<td>${formatCurrency(campaign.total_cost)}</td>`;
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
        ModuleRegistry.register(WasteCampaignFinderModule);
    }
})();
