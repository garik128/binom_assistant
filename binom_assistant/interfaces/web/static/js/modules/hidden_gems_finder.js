/**
 * Модуль: Скрытые точки роста (Hidden Gems Finder)
 * Находит недооцененные кампании с потенциалом роста
 */
(function() {
    const HiddenGemsFinderModule = {
        id: 'hidden_gems_finder',

        translations: {
            total_gems: 'Скрытых жемчужин',
            high_potential: 'Высокий потенциал',
            medium_potential: 'Средний потенциал',
            total_checked: 'Проверено кампаний',
            avg_roi: 'Средний ROI (%)'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по кампаниям за период</li>
                <li>Расчет средних дневных метрик:
                    <ul>
                        <li>avg_daily_spend = total_cost / days_with_data</li>
                    </ul>
                </li>
                <li>Фильтрация: min_daily_spend <= avg_daily_spend <= max_daily_spend</li>
                <li>Расчет дневных ROI для анализа волатильности:
                    <ul>
                        <li>ROI = ((revenue - cost) / cost) * 100</li>
                    </ul>
                </li>
                <li>Расчет статистики ROI:
                    <ul>
                        <li>avg_roi = mean(daily_roi_values)</li>
                        <li>min_roi = min(daily_roi_values)</li>
                        <li>max_roi = max(daily_roi_values)</li>
                    </ul>
                </li>
                <li>Фильтрация: avg_roi >= roi_threshold</li>
                <li>Расчет волатильности (коэффициент вариации):
                    <ul>
                        <li>CV = std_dev(daily_roi) / mean(daily_roi)</li>
                    </ul>
                </li>
                <li>Фильтрация: roi_volatility <= volatility_threshold</li>
                <li>Определение potential_rating:
                    <ul>
                        <li><strong>High</strong>: ROI > 50% AND volatility < 0.2</li>
                        <li><strong>Medium</strong>: остальные</li>
                    </ul>
                </li>
                <li>Сортировка: сначала high potential, потом по avg_roi DESC</li>
            </ol>
        `,

        metrics: `
            <li><strong>Avg ROI</strong> - средний ROI за период (%)</li>
            <li><strong>Min ROI</strong> - минимальный ROI за период (%)</li>
            <li><strong>Max ROI</strong> - максимальный ROI за период (%)</li>
            <li><strong>ROI Volatility</strong> - коэффициент вариации ROI (CV)</li>
            <li><strong>Avg Daily Spend</strong> - средний расход в день ($)</li>
            <li><strong>Total Cost</strong> - общий расход за период ($)</li>
            <li><strong>Total Revenue</strong> - общий доход за период ($)</li>
            <li><strong>Potential Rating</strong> - потенциал роста (high/medium)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            roi_threshold: 'Минимальный ROI (%)',
            max_daily_spend: 'Максимальный расход в день ($)',
            min_daily_spend: 'Минимальный расход в день ($)',
            volatility_threshold: 'Порог волатильности'
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
                                    ${renderSortableHeader('avg_roi', 'Средний ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('min_roi', 'Диапазон ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_volatility', 'Волатильность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_daily_spend', 'Расход в день ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Всего расход ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Всего доход ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('potential_rating', 'Потенциал', 'text', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет potential badge
                    let potentialClass = 'badge-secondary';
                    let potentialLabel = 'Средний';
                    if (campaign.potential_rating === 'high') {
                        potentialClass = 'badge-success';
                        potentialLabel = 'Высокий';
                    } else if (campaign.potential_rating === 'medium') {
                        potentialClass = 'badge-info';
                        potentialLabel = 'Средний';
                    }

                    // Цвет для ROI
                    let roiClass = 'text-success';
                    if (campaign.avg_roi < 50) {
                        roiClass = 'text-info';
                    }

                    // Цвет для волатильности
                    let volatilityClass = 'text-success';
                    if (campaign.roi_volatility > 0.2) {
                        volatilityClass = 'text-warning';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="${roiClass}">
                                    <strong>${campaign.avg_roi.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                ${campaign.min_roi.toFixed(1)}% - ${campaign.max_roi.toFixed(1)}%
                            </td>
                            <td>
                                <span class="${volatilityClass}">
                                    ${campaign.roi_volatility.toFixed(2)}
                                </span>
                                <br><small class="text-muted">${campaign.roi_volatility < 0.2 ? 'низкая' : campaign.roi_volatility < 0.3 ? 'средняя' : 'высокая'}</small>
                            </td>
                            <td>
                                <strong>$${campaign.avg_daily_spend.toFixed(2)}</strong>
                            </td>
                            <td>
                                $${campaign.total_cost.toFixed(2)}
                            </td>
                            <td>
                                <span class="text-success">
                                    $${campaign.total_revenue.toFixed(2)}
                                </span>
                            </td>
                            <td>
                                <span class="badge ${potentialClass}">
                                    ${potentialLabel}
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
                        <strong>Мин. ROI:</strong> ${params.roi_threshold || 30}% |
                        <strong>Расход в день:</strong> $${params.min_daily_spend || 1.0} - $${params.max_daily_spend || 5.0} |
                        <strong>Макс. волатильность:</strong> ${params.volatility_threshold || 0.3}
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
        ModuleRegistry.register(HiddenGemsFinderModule);
    }
})();
