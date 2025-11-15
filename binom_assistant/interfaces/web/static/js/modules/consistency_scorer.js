/**
 * Модуль: Стабильность (Consistency Scorer)
 * Оценка стабильности прибыли во времени
 */
(function() {
    const ConsistencyScorerModule = {
        id: 'consistency_scorer',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_high: 'Высокая консистентность',
            total_medium: 'Средняя консистентность',
            total_low: 'Низкая консистентность',
            avg_consistency_score: 'Средний индекс консистентности',
            best_consistency_score: 'Лучший индекс',
            worst_consistency_score: 'Худший индекс',
            avg_profitable_days_pct: 'Средний % прибыльных дней'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за указанный период (по умолчанию 14 дней)</li>
                <li>Для каждого дня определяется прибыльность (revenue - cost > 0)</li>
                <li>Рассчитывается процент прибыльных дней из общего количества дней с данными</li>
                <li>Вычисляется соотношение прибыльных к убыточным дням (profit/loss ratio)</li>
                <li>Определяется максимальная просадка (drawdown) - максимальное падение от пикового значения прибыли</li>
                <li>Рассчитывается процент максимальной просадки от пикового значения</li>
                <li>Индекс консистентности (0-100) складывается из: 50% - процент прибыльных дней, 30% - соотношение прибыль/убыток (макс 10:1), 20% - инверсия просадки</li>
                <li>Классификация: высокая (≥70 по умолчанию), средняя (40-70), низкая (<40)</li>
                <li>Фильтруются кампании с минимальным расходом ($1/день) и количеством дней с данными (7 дней)</li>
                <li>Формируются алерты для высококонсистентных кампаний (возможности масштабирования) и низкоконсистентных (предупреждения)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Индекс консистентности</strong> - общая оценка стабильности прибыли (0-100), чем выше, тем стабильнее</li>
            <li><strong>Прибыльных дней</strong> - количество дней с положительной прибылью</li>
            <li><strong>Убыточных дней</strong> - количество дней с отрицательной прибылью или нулевой</li>
            <li><strong>Процент прибыльных дней</strong> - доля прибыльных дней от общего количества, %</li>
            <li><strong>Соотношение прибыль/убыток</strong> - отношение прибыльных дней к убыточным (например, 3:1)</li>
            <li><strong>Максимальная просадка</strong> - максимальное падение прибыли от пикового значения, $</li>
            <li><strong>Максимальная просадка %</strong> - процент просадки от пикового значения, %</li>
            <li><strong>Общая прибыль</strong> - суммарная прибыль за период (revenue - cost), $</li>
            <li><strong>Средний ROI</strong> - средняя рентабельность за период, %</li>
            <li><strong>Дней с данными</strong> - количество дней с активностью в анализируемом периоде</li>
            <li><strong>Классификация</strong> - high (высокая), medium (средняя), low (низкая)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_spend: 'Минимальный расход в день',
            min_days_with_data: 'Минимум дней с данными',
            profitability_threshold: 'Порог высокой консистентности (%)'
        },

        /**
         * Отрисовка таблицы для consistency_scorer
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
                                    ${renderSortableHeader('consistency_score', 'Индекс', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('consistency_class', 'Класс', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('profitable_days_pct', 'Прибыльных %', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('profit_loss_ratio', 'Соотношение', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('max_drawdown_pct', 'Просадка %', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'Средний ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_with_data', 'Дней', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Индекс консистентности с цветом
                    let scoreClass = 'text-success';
                    if (campaign.consistency_score < 40) scoreClass = 'text-danger';
                    else if (campaign.consistency_score < 70) scoreClass = 'text-warning';

                    // Класс badge
                    const classBadges = {
                        'high': '<span class="badge bg-success">Высокая</span>',
                        'medium': '<span class="badge bg-warning">Средняя</span>',
                        'low': '<span class="badge bg-danger">Низкая</span>'
                    };
                    const classBadge = classBadges[campaign.consistency_class] || campaign.consistency_class;

                    // ROI цвет
                    const roiClass = campaign.avg_roi >= 0 ? 'text-success' : 'text-danger';

                    // Прибыль цвет
                    const profitClass = campaign.total_profit >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${scoreClass}">${campaign.consistency_score.toFixed(1)}</strong></td>
                            <td>${classBadge}</td>
                            <td>${campaign.profitable_days_pct.toFixed(1)}% <small class="text-muted">(${campaign.profitable_days}/${campaign.days_with_data})</small></td>
                            <td>${campaign.profit_loss_ratio.toFixed(2)}</td>
                            <td>${campaign.max_drawdown_pct.toFixed(1)}%</td>
                            <td class="${roiClass}">${campaign.avg_roi.toFixed(2)}%</td>
                            <td class="${profitClass}">${formatCurrency(campaign.total_profit)}</td>
                            <td>${campaign.days_with_data}</td>
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
        ModuleRegistry.register(ConsistencyScorerModule);
    }
})();
