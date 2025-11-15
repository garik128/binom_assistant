/**
 * Модуль: Устойчивость результатов (Performance Stability)
 * Анализ устойчивости результатов во времени
 */
(function() {
    const PerformanceStabilityModule = {
        id: 'performance_stability',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_high: 'Высокая устойчивость',
            total_medium: 'Средняя устойчивость',
            total_low: 'Низкая устойчивость',
            avg_stability_score: 'Средний индекс устойчивости',
            best_stability_score: 'Лучший индекс',
            worst_stability_score: 'Худший индекс',
            avg_weekday_weekend_diff: 'Средняя разница будни/выходные (%)',
            avg_cv_roi: 'Средняя волатильность ROI (CV, %)'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за указанный период (по умолчанию 21 день)</li>
                <li>Данные разделяются на будни (понедельник-пятница) и выходные (суббота-воскресенье)</li>
                <li>Рассчитывается средний ROI отдельно для будней и выходных</li>
                <li>Вычисляется разница между средним ROI будней и выходных (% отклонения)</li>
                <li>Определяется стандартное отклонение ROI и коэффициент вариации (CV) для оценки волатильности</li>
                <li>Выявляются выбросы - значения ROI, выходящие за пределы ±2σ от среднего</li>
                <li>Индекс устойчивости (0-100) складывается из: 40% - низкая разница будни/выходные, 30% - низкая волатильность (CV), 30% - малое количество выбросов</li>
                <li>Классификация: высокая (≥70 по умолчанию), средняя (40-70), низкая (<40)</li>
                <li>Фильтруются кампании с минимальным расходом ($1/день) и количеством дней с данными (10 дней)</li>
                <li>Формируются алерты для устойчивых кампаний (возможности масштабирования) и неустойчивых (требуется оптимизация)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Индекс устойчивости</strong> - общая оценка стабильности результатов (0-100), чем выше, тем устойчивее</li>
            <li><strong>Будни дней</strong> - количество будних дней с данными в периоде</li>
            <li><strong>Выходных дней</strong> - количество выходных дней с данными в периоде</li>
            <li><strong>ROI будни</strong> - средний ROI в будние дни, %</li>
            <li><strong>ROI выходные</strong> - средний ROI в выходные дни, %</li>
            <li><strong>Разница будни/выходные</strong> - процент отклонения ROI выходных от будней, %</li>
            <li><strong>Стандартное отклонение ROI</strong> - мера разброса значений ROI</li>
            <li><strong>Коэффициент вариации (CV)</strong> - нормализованная волатильность ROI, %</li>
            <li><strong>Выбросов</strong> - количество дней с аномальными значениями ROI (за ±2σ)</li>
            <li><strong>Выбросов %</strong> - процент дней с выбросами от общего количества дней, %</li>
            <li><strong>Общая прибыль</strong> - суммарная прибыль за период (revenue - cost), $</li>
            <li><strong>Общий ROI</strong> - средняя рентабельность за весь период, %</li>
            <li><strong>Дней с данными</strong> - количество дней с активностью в анализируемом периоде</li>
            <li><strong>Классификация</strong> - high (высокая), medium (средняя), low (низкая)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_spend: 'Минимальный расход в день',
            min_days_with_data: 'Минимум дней с данными',
            weekday_weekend_diff_threshold: 'Порог разницы будни/выходные (%)',
            stability_score_threshold: 'Порог высокой устойчивости'
        },

        /**
         * Отрисовка таблицы для performance_stability
         */
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
                                    ${renderSortableHeader('stability_score', 'Индекс', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('stability_class', 'Класс', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('weekday_weekend_roi_diff', 'Разница будни/выходные', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('weekday_avg_roi', 'ROI будни', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('weekend_avg_roi', 'ROI выходные', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cv_roi', 'Волатильность (CV)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('outliers_pct', 'Выбросов %', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('overall_roi', 'Общий ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Индекс устойчивости с цветом
                    let scoreClass = 'text-success';
                    if (campaign.stability_score < 40) scoreClass = 'text-danger';
                    else if (campaign.stability_score < 70) scoreClass = 'text-warning';

                    // Класс badge
                    const classBadges = {
                        'high': '<span class="badge bg-success">Высокая</span>',
                        'medium': '<span class="badge bg-warning">Средняя</span>',
                        'low': '<span class="badge bg-danger">Низкая</span>'
                    };
                    const classBadge = classBadges[campaign.stability_class] || campaign.stability_class;

                    // Разница будни/выходные - чем больше, тем хуже
                    let diffClass = 'text-success';
                    if (campaign.weekday_weekend_roi_diff > 50) diffClass = 'text-danger';
                    else if (campaign.weekday_weekend_roi_diff > 30) diffClass = 'text-warning';

                    // ROI цвет
                    const weekdayRoiClass = campaign.weekday_avg_roi >= 0 ? 'text-success' : 'text-danger';
                    const weekendRoiClass = campaign.weekend_avg_roi >= 0 ? 'text-success' : 'text-danger';
                    const overallRoiClass = campaign.overall_roi >= 0 ? 'text-success' : 'text-danger';

                    // Прибыль цвет
                    const profitClass = campaign.total_profit >= 0 ? 'text-success' : 'text-danger';

                    // Волатильность - чем больше, тем хуже
                    let cvClass = 'text-success';
                    if (campaign.cv_roi > 80) cvClass = 'text-danger';
                    else if (campaign.cv_roi > 40) cvClass = 'text-warning';

                    // Выбросы - чем больше, тем хуже
                    let outliersClass = 'text-success';
                    if (campaign.outliers_pct > 15) outliersClass = 'text-danger';
                    else if (campaign.outliers_pct > 8) outliersClass = 'text-warning';

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${scoreClass}">${campaign.stability_score.toFixed(1)}</strong></td>
                            <td>${classBadge}</td>
                            <td class="${diffClass}">${campaign.weekday_weekend_roi_diff.toFixed(1)}%</td>
                            <td class="${weekdayRoiClass}">${campaign.weekday_avg_roi.toFixed(2)}% <small class="text-muted">(${campaign.weekday_days}д)</small></td>
                            <td class="${weekendRoiClass}">${campaign.weekend_avg_roi.toFixed(2)}% <small class="text-muted">(${campaign.weekend_days}д)</small></td>
                            <td class="${cvClass}">${campaign.cv_roi.toFixed(1)}%</td>
                            <td class="${outliersClass}">${campaign.outliers_pct.toFixed(1)}% <small class="text-muted">(${campaign.outliers_count})</small></td>
                            <td class="${overallRoiClass}">${campaign.overall_roi.toFixed(2)}%</td>
                            <td class="${profitClass}">${formatCurrency(campaign.total_profit)}</td>
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
        ModuleRegistry.register(PerformanceStabilityModule);
    }
})();
