/**
 * Модуль: Оптимизация бюджета (Budget Optimizer)
 * Предлагает оптимальное перераспределение бюджетов между кампаниями
 */
(function() {
    const BudgetOptimizerModule = {
        id: 'budget_optimizer',

        translations: {
            campaign_name: 'Название кампании',
            current_daily_spend: 'Текущий дневной бюджет',
            recommended_daily_spend: 'Рекомендуемый бюджет',
            change_percent: 'Изменение (%)',
            reason: 'Причина',
            current_roi: 'Текущий ROI',
            current_volatility: 'Волатильность',
            potential_improvement: 'Потенциальное улучшение',
            total_campaigns: 'Всего кампаний',
            top_campaigns: 'Кампании для увеличения',
            bottom_campaigns: 'Кампании для снижения',
            total_current_spend: 'Текущий бюджет',
            estimated_new_spend: 'Новый бюджет'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Фильтрация шума (расход < $1 или клики < 50)</li>
                <li>Расчет производительности каждой кампании:
                    <ol>
                        <li><strong>ROI</strong>: ((revenue - cost) / cost) * 100</li>
                        <li><strong>Волатильность</strong>: коэффициент вариации дневного ROI</li>
                        <li><strong>Риск</strong>: высокая волатильность = высокий риск</li>
                    </ol>
                </li>
                <li>Сегментирование кампаний:
                    <ul>
                        <li><strong>Топ 20%</strong> по ROI: рекомендация увеличения бюджета</li>
                        <li><strong>Низ 20%</strong> по ROI: рекомендация снижения бюджета</li>
                    </ul>
                </li>
                <li>Расчет рекомендуемого изменения:
                    <ul>
                        <li>Для топ-кампаний: change = (roi_score * max_change) - (volatility_penalty)</li>
                        <li>Макс изменение ограничено параметром max_change_percent (по умолчанию 30%)</li>
                        <li>Учитывается волатильность как фактор риска</li>
                    </ul>
                </li>
                <li>Оценка потенциала улучшения:
                    <ul>
                        <li>Расчет текущего средневзвешенного ROI</li>
                        <li>Расчет нового средневзвешенного ROI с учетом рекомендаций</li>
                        <li>Потенциал = ((новый ROI - текущий ROI) / |текущий ROI|) * 100</li>
                    </ul>
                </li>
            </ol>
        `,

        metrics: `
            <li><strong>Potential Improvement</strong> - потенциальное улучшение ROI портфеля в % благодаря перераспределению</li>
            <li><strong>Current Daily Spend</strong> - текущий средний дневной расход на кампанию</li>
            <li><strong>Recommended Daily Spend</strong> - рекомендуемый средний дневной расход</li>
            <li><strong>Change Percent</strong> - рекомендуемое изменение бюджета в процентах</li>
            <li><strong>Current ROI</strong> - текущий ROI кампании за период</li>
            <li><strong>Volatility</strong> - волатильность (нестабильность) производительности кампании</li>
            <li><strong>Top Campaigns</strong> - количество кампаний с рекомендацией увеличения</li>
            <li><strong>Bottom Campaigns</strong> - количество кампаний с рекомендацией снижения</li>
            <li><strong>Total Current Spend</strong> - общий текущий расход портфеля за период</li>
            <li><strong>Estimated New Spend</strong> - предполагаемый новый расход при применении рекомендаций</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            max_change_percent: 'Макс. изменение бюджета (%)',
            min_cost: 'Минимальный расход ($)',
            min_clicks: 'Минимум кликов'
        },

        renderTable: function(results, container) {
            if (!results.data) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const recommendations = data.recommendations || [];
            const potential_improvement = data.potential_improvement || 0;
            const summary = data.summary || {};
            const period = data.period || {};
            const sortState = { column: null, direction: 'asc' };

            const render = () => {
                let html = '';

                // Таблица рекомендаций (summary отрисовывается отдельно в resultsSummary)
                if (recommendations.length > 0) {
                    html += `
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Кампания</th>
                                        ${renderSortableHeader('current_daily_spend', 'Текущий бюджет', 'number', sortState.column, sortState.direction)}
                                        ${renderSortableHeader('recommended_daily_spend', 'Рекомендуемый', 'number', sortState.column, sortState.direction)}
                                        ${renderSortableHeader('change_percent', 'Изменение (%)', 'number', sortState.column, sortState.direction)}
                                        ${renderSortableHeader('current_roi', 'ROI (%)', 'number', sortState.column, sortState.direction)}
                                        ${renderSortableHeader('current_volatility', 'Волатильность (%)', 'number', sortState.column, sortState.direction)}
                                        <th>Причина</th>
                                        <th>Binom</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;

                    recommendations.forEach(rec => {
                        const binomId = rec.binom_id || rec.campaign_id;
                        const changeIcon = rec.change_percent > 0 ? '↑' : '↓';
                        const changeClass = rec.change_percent > 0 ? 'text-success' : 'text-danger';

                        html += `
                            <tr>
                                <td><strong>[${binomId}] ${escapeHtml(rec.name)}</strong></td>
                                <td>${formatCurrency(rec.current_daily_spend)}</td>
                                <td class="${changeClass}">${formatCurrency(rec.recommended_daily_spend)}</td>
                                <td class="${changeClass}"><strong>${changeIcon} ${Math.abs(rec.change_percent).toFixed(1)}%</strong></td>
                                <td class="${rec.current_roi >= 0 ? 'text-success' : 'text-danger'}">${rec.current_roi.toFixed(1)}%</td>
                                <td>${rec.current_volatility.toFixed(1)}%</td>
                                <td><small>${rec.reason}</small></td>
                                <td>${renderBinomLink(binomId)}</td>
                            </tr>
                        `;
                    });

                    html += `
                                </tbody>
                            </table>
                        </div>
                    `;
                } else {
                    html += '<p class="text-muted">Нет рекомендаций для отображения</p>';
                }

                // Info banner
                html += `
                    <div class="info-banner">
                        <strong>Период:</strong> ${period.days || 7} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, recommendations, (col, dir) => render(), sortState);
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(BudgetOptimizerModule);
    }
})();
