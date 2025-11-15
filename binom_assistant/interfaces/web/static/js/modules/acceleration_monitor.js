/**
 * Модуль: Ускорение динамики (Acceleration Monitor)
 * Измеряет ускорение или замедление роста метрик
 */
(function() {
    const AccelerationMonitorModule = {
        id: 'acceleration_monitor',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_accelerating: 'Ускоряющихся',
            total_stable: 'Стабильных',
            total_decelerating: 'Замедляющихся',
            avg_acceleration: 'Среднее ускорение',
            max_acceleration: 'Максимальное ускорение',
            min_acceleration: 'Минимальное ускорение'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за выбранный период (по умолчанию 7 дней включая сегодня)</li>
                <li>Для каждого дня вычисляется ROI кампании ((Revenue - Cost) / Cost * 100)</li>
                <li>Применяется скользящее среднее (moving average) с указанным окном сглаживания (по умолчанию 3 дня) для уменьшения шума</li>
                <li>Вычисляется первая производная (скорость изменения) - разность между соседними точками сглаженного ROI</li>
                <li>Вычисляется вторая производная (ускорение) - разность между соседними точками скорости изменения</li>
                <li>Рассчитываются средние значения: средняя скорость изменения и среднее ускорение</li>
                <li>Текущее ускорение определяется как последнее значение второй производной</li>
                <li>Кампании классифицируются по текущему ускорению: ускоряются (>2), стабильные (-2 до +2), замедляются (<-2)</li>
                <li>Фильтруются кампании с минимальным средним расходом ($1/день) и минимальными кликами (20 за период)</li>
                <li>Формируются алерты для сильных изменений ускорения (>5 или <-5)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Текущее ускорение</strong> - значение второй производной ROI, показывает ускорение/торможение роста</li>
            <li><strong>Среднее ускорение</strong> - средняя вторая производная ROI за период анализа</li>
            <li><strong>Текущая скорость</strong> - последнее значение первой производной ROI (скорость изменения)</li>
            <li><strong>Средняя скорость</strong> - средняя первая производная ROI за период</li>
            <li><strong>Текущий ROI</strong> - последнее сглаженное значение ROI, %</li>
            <li><strong>Средний ROI</strong> - среднее сглаженное значение ROI за период, %</li>
            <li><strong>Общий расход</strong> - суммарный расход за весь период анализа, $</li>
            <li><strong>Общий доход</strong> - суммарная прибыль за весь период, $</li>
            <li><strong>Клики</strong> - общее количество кликов за период</li>
            <li><strong>Лиды</strong> - общее количество лидов за период</li>
            <li><strong>Категория</strong> - классификация: accelerating (ускоряется), stable (стабильно), decelerating (замедляется)</li>
            <li><strong>Дней проанализировано</strong> - количество дней с данными в периоде</li>
            <li><strong>Окно сглаживания</strong> - размер окна для скользящего среднего (по умолчанию 3 дня)</li>
            <li><strong>Минимальный расход в день</strong> - порог фильтрации ($1 по умолчанию)</li>
            <li><strong>Минимум кликов за период</strong> - порог фильтрации (20 по умолчанию)</li>
        `,

        paramTranslations: {
            days: 'Период анализа',
            min_spend: 'Минимальный расход в день',
            min_clicks: 'Минимум кликов за период',
            smoothing_window: 'Окно сглаживания'
        },

        /**
         * Отрисовка таблицы для acceleration_monitor
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
                                    ${renderSortableHeader('current_acceleration', 'Ускорение', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('category', 'Категория', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_velocity', 'Скорость', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'ROI текущий', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'ROI средний', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_clicks', 'Клики', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_leads', 'Лиды', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Ускорение с цветом
                    let accelerationClass = 'text-muted';
                    if (campaign.current_acceleration > 2) accelerationClass = 'text-success';
                    else if (campaign.current_acceleration < -2) accelerationClass = 'text-danger';

                    // Скорость с цветом
                    let velocityClass = 'text-muted';
                    if (campaign.current_velocity > 0) velocityClass = 'text-success';
                    else if (campaign.current_velocity < 0) velocityClass = 'text-danger';

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
                            <td><strong class="${accelerationClass}">${campaign.current_acceleration > 0 ? '+' : ''}${campaign.current_acceleration.toFixed(2)}</strong></td>
                            <td>${categoryBadge}</td>
                            <td class="${velocityClass}">${campaign.current_velocity > 0 ? '+' : ''}${campaign.current_velocity.toFixed(2)}</td>
                            <td class="${campaign.current_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.current_roi.toFixed(2)}%</td>
                            <td class="${campaign.avg_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.avg_roi.toFixed(2)}%</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
                            <td>${campaign.total_clicks}</td>
                            <td>${campaign.total_leads}</td>
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
        ModuleRegistry.register(AccelerationMonitorModule);
    }
})();
