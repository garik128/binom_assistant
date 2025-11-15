/**
 * Модуль: Восстановление (Recovery Detector)
 * Поиск восстанавливающихся после просадки кампаний
 */
(function() {
    const RecoveryDetectorModule = {
        id: 'recovery_detector',

        translations: {
            total_recovering: 'Восстанавливающихся кампаний',
            total_analyzed: 'Проанализировано кампаний',
            total_in_drawdown: 'В просадке',
            total_stable: 'Стабильных',
            avg_recovery_strength: 'Средняя сила восстановления',
            strong_recoveries: 'Сильных восстановлений',
            avg_roi_improvement: 'Среднее улучшение ROI'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за заданный период (по умолчанию 14 дней)</li>
                <li>Для каждой кампании вычисляется ежедневный ROI и CR</li>
                <li>Определяются периоды просадки - дни подряд с ROI ниже порога (по умолчанию -30%)</li>
                <li>Находится последняя просадка и минимальный ROI в ней</li>
                <li>Анализируется период после просадки на предмет восстановления</li>
                <li>Проверяется рост ROI в последние N дней подряд (по умолчанию 2 дня)</li>
                <li>Вычисляется улучшение ROI от минимума (должно быть > порога, по умолчанию 20%)</li>
                <li>Проверяется положительная динамика CR (сравнение средней CR в просадке и текущей)</li>
                <li>Рассчитывается сила восстановления (0-100) на основе улучшения ROI и CR</li>
                <li>Кампании классифицируются по силе восстановления: сильное, умеренное, слабое</li>
            </ol>
        `,

        metrics: `
            <li><strong>Сила восстановления</strong> - интегральный показатель от 0 до 100, учитывающий улучшение ROI и CR</li>
            <li><strong>Текущий ROI</strong> - рентабельность в последний день восстановления ((Revenue - Cost) / Cost * 100), %</li>
            <li><strong>Минимальный ROI</strong> - худший ROI в период просадки, %</li>
            <li><strong>Улучшение ROI</strong> - разница между текущим ROI и минимальным, %</li>
            <li><strong>Текущая CR</strong> - конверсия в последний день восстановления (Leads / Clicks * 100), %</li>
            <li><strong>Улучшение CR</strong> - разница между текущей CR и средней CR в просадке, %</li>
            <li><strong>Дней в просадке</strong> - количество дней подряд с плохим ROI</li>
            <li><strong>Дней восстановления</strong> - количество дней с момента окончания просадки</li>
            <li><strong>Период просадки</strong> - даты начала и окончания периода с плохим ROI</li>
            <li><strong>Общий расход/доход</strong> - суммарные затраты и прибыль за весь анализируемый период</li>
            <li><strong>Средний ROI</strong> - средняя рентабельность за весь период, %</li>
            <li><strong>Severity</strong> - уровень важности: high (сильное восстановление к прибыли), medium (умеренное), low (слабое)</li>
        `,

        paramTranslations: {
            analysis_days: 'Дней для анализа',
            min_bad_days: 'Минимум дней в просадке',
            bad_roi_threshold: 'Порог плохого ROI',
            recovery_days: 'Дней роста для восстановления',
            recovery_improvement: 'Улучшение от дна',
            min_spend: 'Минимальный расход',
            min_clicks: 'Минимум кликов'
        },

        /**
         * Отрисовка таблицы для recovery_detector
         */
        renderTable: function(results, container) {
            if (!results.data || !results.data.recovering_campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.recovering_campaigns;
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('recovery_strength', 'Сила', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'ROI текущий', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('min_roi', 'ROI мин.', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_improvement', 'Улучшение', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_cr', 'CR текущая', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('bad_period_days', 'Дней в просадке', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    <th>Период просадки</th>
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Сила восстановления с цветом
                    let strengthClass = 'text-muted';
                    if (campaign.recovery_strength >= 70) strengthClass = 'text-success';
                    else if (campaign.recovery_strength >= 50) strengthClass = 'text-primary';
                    else strengthClass = 'text-warning';

                    // Severity badge
                    const severityBadges = {
                        'high': '<span class="badge bg-success">Сильное</span>',
                        'medium': '<span class="badge bg-primary">Умеренное</span>',
                        'low': '<span class="badge bg-warning">Слабое</span>'
                    };
                    const severityBadge = severityBadges[campaign.severity] || campaign.severity;

                    // Форматирование периода просадки
                    const badPeriod = `${campaign.bad_period_start} - ${campaign.bad_period_end}`;

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small><br>
                                ${severityBadge}
                            </td>
                            <td><strong class="${strengthClass}">${campaign.recovery_strength.toFixed(1)}</strong></td>
                            <td class="${campaign.current_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.current_roi.toFixed(2)}%</td>
                            <td class="text-danger">${campaign.min_roi.toFixed(2)}%</td>
                            <td class="text-success">+${campaign.roi_improvement.toFixed(2)}%</td>
                            <td>${campaign.current_cr.toFixed(2)}%</td>
                            <td>${campaign.bad_period_days}</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
                            <td><small>${badPeriod}</small></td>
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
        ModuleRegistry.register(RecoveryDetectorModule);
    }
})();
