/**
 * Модуль: Этап кампании
 * Определяет стадию жизненного цикла кампании
 */
(function() {
    const CampaignLifecycleStageModule = {
        id: 'campaign_lifecycle_stage',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            launch_count: 'Запуск',
            growth_count: 'Рост',
            maturity_count: 'Зрелость',
            decline_count: 'Упадок',
            stagnation_count: 'Застой',
            dead_count: 'Мертвая'
        },

        algorithm: `
            <ol>
                <li>Загрузка исторических данных за последние 14 дней для каждой кампании</li>
                <li>Подсчет дней активности (дней с расходом > $0)</li>
                <li>Расчет трендов ROI и расходов используя линейную регрессию</li>
                <li>Определение стадии жизненного цикла:
                    <ul>
                        <li><strong>Launch</strong> (запуск): менее 3 дней активности</li>
                        <li><strong>Dead</strong> (мертвая): нет расхода последние 7 дней</li>
                        <li><strong>Stagnation</strong> (застой): средний расход < порога и ROI < 0</li>
                        <li><strong>Growth</strong> (рост): ROI тренд > 5%/день и расход растет</li>
                        <li><strong>Decline</strong> (упадок): ROI тренд < -5%/день</li>
                        <li><strong>Maturity</strong> (зрелость): стабильные показатели</li>
                    </ul>
                </li>
                <li>Расчет уровня уверенности (confidence) на основе R² регрессий</li>
                <li>Сортировка по приоритету: упадок → застой → мертвая → запуск → рост → зрелость</li>
            </ol>
        `,

        metrics: `
            <li><strong>Stage</strong> - стадия жизненного цикла (launch/growth/maturity/decline/stagnation/dead)</li>
            <li><strong>Days Active</strong> - количество дней с активностью (cost > 0)</li>
            <li><strong>ROI Trend</strong> - тренд ROI (%/день), положительный = рост, отрицательный = падение</li>
            <li><strong>Spend Trend</strong> - тренд расходов ($/день), показывает динамику бюджета</li>
            <li><strong>Confidence</strong> - уровень уверенности в классификации (0-1), основан на R²</li>
            <li><strong>Current ROI</strong> - текущий средний ROI за период, %</li>
            <li><strong>Avg Daily Spend</strong> - средний расход в день, $</li>
        `,

        paramTranslations: {
            min_spend: 'Минимальный расход',
            days_history: 'Дней истории',
            stagnation_threshold: 'Порог застоя'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.campaigns;
            const period = results.data.period || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('stage_label', 'Стадия', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_active', 'Дней активности', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_trend', 'ROI тренд (%/день)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('spend_trend', 'Spend тренд ($/день)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'Текущий ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_daily_spend', 'Расход/день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('confidence', 'Уверенность', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет badge для стадии
                    let stageBadgeClass = '';
                    switch(campaign.stage) {
                        case 'launch':
                            stageBadgeClass = 'badge-info';  // синий
                            break;
                        case 'growth':
                            stageBadgeClass = 'badge-success';  // зеленый
                            break;
                        case 'maturity':
                            stageBadgeClass = 'badge-primary';  // голубой
                            break;
                        case 'decline':
                            stageBadgeClass = 'badge-danger';  // красный
                            break;
                        case 'stagnation':
                            stageBadgeClass = 'badge-warning';  // желтый
                            break;
                        case 'dead':
                            stageBadgeClass = 'badge-secondary';  // серый
                            break;
                    }

                    // Цвет для ROI тренда
                    const roiTrendClass = campaign.roi_trend > 0 ? 'text-success' :
                                         campaign.roi_trend < 0 ? 'text-danger' : 'text-muted';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td><span class="badge ${stageBadgeClass}">${campaign.stage_label}</span></td>
                            <td>${campaign.days_active}</td>
                            <td class="${roiTrendClass}">${campaign.roi_trend.toFixed(2)}</td>
                            <td>${campaign.spend_trend.toFixed(2)}</td>
                            <td>${formatROI(campaign.current_roi)}</td>
                            <td>${formatCurrency(campaign.avg_daily_spend)}</td>
                            <td>${(campaign.confidence * 100).toFixed(0)}%</td>
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
                        <strong>Период анализа:</strong> ${period.days_history || 14} дней |
                        <strong>Всего кампаний:</strong> ${campaigns.length}
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
        ModuleRegistry.register(CampaignLifecycleStageModule);
    }
})();
