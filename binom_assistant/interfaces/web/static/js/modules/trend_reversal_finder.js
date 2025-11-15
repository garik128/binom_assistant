/**
 * Модуль: Разворот тренда (Trend Reversal Finder)
 * Обнаружение смены тренда с роста на падение
 */
(function() {
    const TrendReversalFinderModule = {
        id: 'trend_reversal_finder',

        translations: {
            total_reversals: 'Обнаружено разворотов',
            total_analyzed: 'Проанализировано кампаний',
            total_growing: 'В росте',
            total_declining: 'В снижении',
            total_stable: 'Стабильных',
            total_filtered_out: 'Отфильтровано (не хватает данных/порогов)',
            critical_reversals: 'Критичных разворотов',
            high_reversals: 'Высоких разворотов',
            avg_reversal_strength: 'Средняя сила разворота',
            avg_roi_drop: 'Среднее падение ROI',
            avg_slope_change: 'Среднее изменение наклона'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за период анализа (по умолчанию 14 дней включая сегодня)</li>
                <li>Для каждой кампании вычисляется ROI для каждого дня периода</li>
                <li>Проверяется стабильность объемов расходов (вариация не должна превышать 20% по умолчанию)</li>
                <li>Ищется период роста ROI: минимум 5 дней подряд с растущим ROI</li>
                <li>Для периода роста вычисляется линейная регрессия и угол наклона тренда</li>
                <li>Проверяется значимость тренда роста через R² (должен быть > 0.5)</li>
                <li>После периода роста ищется период снижения: минимум 2 дня подряд с падающим ROI</li>
                <li>Для периода снижения вычисляется линейная регрессия и угол наклона</li>
                <li>Рассчитывается изменение угла наклона между ростом и падением (в градусах)</li>
                <li>Если изменение наклона превышает порог (30° по умолчанию) - фиксируется разворот тренда</li>
                <li>Вычисляется сила разворота (0-100) на основе изменения угла и падения ROI</li>
                <li>Присваивается уровень критичности: critical (>60° и падение >30%), high (>45° или падение >20%), medium, low</li>
                <li>Фильтруются кампании по минимальным порогам расхода и кликов</li>
                <li>Формируются алерты для критичных и сильных разворотов</li>
            </ol>
        `,

        metrics: `
            <li><strong>Сила разворота</strong> - комплексный показатель от 0 до 100, учитывающий изменение угла наклона и падение ROI</li>
            <li><strong>Изменение наклона</strong> - разница углов наклона между трендом роста и трендом снижения (градусы)</li>
            <li><strong>ROI в точке разворота</strong> - значение ROI на пике тренда роста перед началом снижения, %</li>
            <li><strong>Текущий ROI</strong> - значение ROI на последний день анализа, %</li>
            <li><strong>Падение ROI</strong> - абсолютное падение ROI от точки разворота до текущего значения, %</li>
            <li><strong>Дней роста</strong> - количество дней в периоде роста</li>
            <li><strong>Дней снижения</strong> - количество дней в периоде снижения</li>
            <li><strong>Угол роста</strong> - угол наклона линии тренда в период роста (градусы)</li>
            <li><strong>Угол снижения</strong> - угол наклона линии тренда в период снижения (градусы)</li>
            <li><strong>R² роста</strong> - коэффициент детерминации для линейной регрессии периода роста (0-1, >0.5 = значимый тренд)</li>
            <li><strong>Стабильность объема</strong> - показатель стабильности расходов (100% = идеально стабильно)</li>
            <li><strong>Уровень критичности</strong> - critical (очень сильный разворот), high (сильный), medium (умеренный), low (слабый)</li>
            <li><strong>Минимальный расход в день</strong> - порог фильтрации ($1 по умолчанию)</li>
            <li><strong>Минимум кликов за период</strong> - порог фильтрации (100 по умолчанию)</li>
        `,

        paramTranslations: {
            analysis_days: 'Дней для анализа',
            growth_days: 'Минимум дней роста',
            decline_days: 'Минимум дней снижения',
            min_slope_change_degrees: 'Изменение наклона',
            volume_stability_threshold: 'Стабильность объема',
            min_spend_per_day: 'Минимальный расход в день',
            min_clicks: 'Минимум кликов'
        },

        /**
         * Отрисовка таблицы для trend_reversal_finder
         */
        renderTable: function(results, container) {
            if (!results.data || !results.data.reversal_campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.reversal_campaigns;
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('reversal_strength', 'Сила разворота', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity', 'Критичность', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('slope_change_degrees', 'Δ Наклон', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_drop', 'Падение ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('reversal_point_roi', 'ROI на пике', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'ROI текущий', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('growth_days_count', 'Дней роста', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('decline_days_count', 'Дней снижения', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Severity badge
                    const severityBadges = {
                        'critical': '<span class="badge bg-danger">Критично</span>',
                        'high': '<span class="badge bg-warning">Высоко</span>',
                        'medium': '<span class="badge bg-info">Средне</span>',
                        'low': '<span class="badge bg-secondary">Низко</span>'
                    };
                    const severityBadge = severityBadges[campaign.severity] || campaign.severity;

                    // Сила разворота с цветом
                    let strengthClass = 'text-muted';
                    if (campaign.reversal_strength >= 70) strengthClass = 'text-danger';
                    else if (campaign.reversal_strength >= 50) strengthClass = 'text-warning';
                    else if (campaign.reversal_strength >= 30) strengthClass = 'text-info';

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${strengthClass}">${campaign.reversal_strength.toFixed(1)}</strong></td>
                            <td>${severityBadge}</td>
                            <td><strong class="text-warning">${campaign.slope_change_degrees.toFixed(1)}°</strong></td>
                            <td class="text-danger"><strong>${campaign.roi_drop.toFixed(2)}%</strong></td>
                            <td class="${campaign.reversal_point_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.reversal_point_roi.toFixed(2)}%</td>
                            <td class="${campaign.current_roi >= 0 ? 'text-success' : 'text-danger'}">${campaign.current_roi.toFixed(2)}%</td>
                            <td><span class="badge bg-success">${campaign.growth_days_count}</span></td>
                            <td><span class="badge bg-danger">${campaign.decline_days_count}</span></td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
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
        ModuleRegistry.register(TrendReversalFinderModule);
    }
})();
