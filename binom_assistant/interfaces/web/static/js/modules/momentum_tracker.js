/**
 * Модуль: Сила импульса (Momentum Tracker)
 * Сравнивает динамику текущей и предыдущей недели
 */
(function() {
    const MomentumTrackerModule = {
        id: 'momentum_tracker',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_accelerating: 'Ускоряющихся',
            total_decelerating: 'Замедляющихся',
            total_stable: 'Стабильных',
            avg_momentum_index: 'Средний индекс momentum',
            strongest_acceleration: 'Максимальное ускорение',
            strongest_deceleration: 'Максимальное замедление'
        },

        algorithm: `
            <ol>
                <li>Определяются два периода: текущая неделя (7 дней включая сегодня) и предыдущая неделя (7 дней до текущей недели)</li>
                <li>Для каждого периода загружается дневная статистика кампаний</li>
                <li>Агрегируются показатели для каждой недели: расход, доход, клики, лиды</li>
                <li>Вычисляются метрики для обеих недель: ROI, EPC, CR</li>
                <li>Рассчитывается изменение (дельта) каждой метрики между неделями</li>
                <li>Вычисляется индекс momentum от -100 до +100 на основе изменения ROI</li>
                <li>Применяется взвешивание по объему трафика для более точной оценки</li>
                <li>Кампании классифицируются: ускоряющиеся (momentum > +15), замедляющиеся (momentum < -15), стабильные</li>
                <li>Фильтруются кампании с минимальными расходами ($5/неделя) и кликами (30/неделя)</li>
                <li>Формируются алерты для сильных изменений momentum (>30 или <-30)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Индекс momentum</strong> - показатель ускорения/замедления от -100 до +100. Положительный = ускорение, отрицательный = замедление</li>
            <li><strong>ROI текущей недели</strong> - рентабельность за текущую неделю ((Revenue - Cost) / Cost * 100), %</li>
            <li><strong>ROI предыдущей недели</strong> - рентабельность за предыдущую неделю, %</li>
            <li><strong>ROI изменение</strong> - разница ROI между текущей и предыдущей неделей, %</li>
            <li><strong>EPC текущей недели</strong> - доход на клик за текущую неделю (Revenue / Clicks), $</li>
            <li><strong>EPC предыдущей недели</strong> - доход на клик за предыдущую неделю, $</li>
            <li><strong>EPC изменение</strong> - разница EPC между неделями, $</li>
            <li><strong>CR текущей недели</strong> - конверсия в лиды за текущую неделю (Leads / Clicks * 100), %</li>
            <li><strong>CR предыдущей недели</strong> - конверсия за предыдущую неделю, %</li>
            <li><strong>CR изменение</strong> - разница CR между неделями, %</li>
            <li><strong>Расход текущей/предыдущей недели</strong> - общие затраты за каждую неделю, $</li>
            <li><strong>Доход текущей/предыдущей недели</strong> - общая прибыль за каждую неделю, $</li>
            <li><strong>Категория</strong> - классификация: accelerating (ускоряется), decelerating (замедляется), stable (стабильно)</li>
            <li><strong>Минимальный расход за неделю</strong> - порог фильтрации ($5 по умолчанию)</li>
            <li><strong>Минимум кликов за неделю</strong> - порог фильтрации (30 по умолчанию)</li>
        `,

        paramTranslations: {
            current_week_days: 'Дней текущей недели',
            previous_week_days: 'Дней предыдущей недели',
            min_spend_per_week: 'Минимальный расход за неделю',
            min_clicks_per_week: 'Минимум кликов за неделю'
        },

        /**
         * Отрисовка таблицы для momentum_tracker
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
                                    ${renderSortableHeader('momentum_index', 'Momentum', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('category', 'Категория', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_change', 'Δ ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'ROI текущий', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_roi', 'ROI предыдущий', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_clicks', 'Клики тек.', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_leads', 'Лиды тек.', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Momentum с цветом
                    let momentumClass = 'text-muted';
                    if (campaign.momentum_index > 15) momentumClass = 'text-success';
                    else if (campaign.momentum_index < -15) momentumClass = 'text-danger';

                    // Категория badge
                    const categoryBadges = {
                        'accelerating': '<span class="badge bg-success">Ускоряется</span>',
                        'decelerating': '<span class="badge bg-danger">Замедляется</span>',
                        'stable': '<span class="badge bg-secondary">Стабильно</span>'
                    };
                    const categoryBadge = categoryBadges[campaign.category] || campaign.category;

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${momentumClass}">${campaign.momentum_index > 0 ? '+' : ''}${campaign.momentum_index.toFixed(1)}</strong></td>
                            <td>${categoryBadge}</td>
                            <td class="${campaign.roi_change >= 0 ? 'text-success' : 'text-danger'}">${campaign.roi_change > 0 ? '+' : ''}${campaign.roi_change.toFixed(2)}%</td>
                            <td class="${campaign.current_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.current_roi.toFixed(2)}%</td>
                            <td class="${campaign.previous_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.previous_roi.toFixed(2)}%</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
                            <td>${campaign.current_clicks}</td>
                            <td>${campaign.current_leads}</td>
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
        ModuleRegistry.register(MomentumTrackerModule);
    }
})();
