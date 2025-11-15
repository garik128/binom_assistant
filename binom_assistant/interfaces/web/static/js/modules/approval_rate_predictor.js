/**
 * Модуль: Прогноз апрувов
 * Прогнозирует approval rate для CPA кампаний на основе исторических данных
 */
(function() {
    const ApprovalRatePredictorModule = {
        id: 'approval_rate_predictor',

        translations: {
            total_analyzed: 'Проанализировано CPA кампаний',
            improving_count: 'С улучшением апрува',
            declining_count: 'С падением апрува',
            stable_count: 'Стабильные',
            avg_r_squared: 'Средняя точность модели (R²)'
        },

        algorithm: `
            <ol>
                <li>Отбор только CPA кампаний (где есть approved leads)</li>
                <li>Загрузка исторических данных approval rate за последние 14 дней</li>
                <li>Расчет approval rate для каждого дня: (a_leads / leads * 100)</li>
                <li>Фильтрация кампаний с минимум 10 лидами за период</li>
                <li>Построение линейной регрессии для определения тренда approval rate</li>
                <li>Экстраполяция тренда на 3-7 дней вперед</li>
                <li>Ограничение прогноза в диапазоне 0-100%</li>
                <li>Классификация трендов: улучшение (+0.1%/день), стабильность, падение (-0.1%/день)</li>
                <li>Приоритет кампаниям с падающим approval rate (критично для CPA)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Current Approve Rate</strong> - текущий процент апрува (последний день), %</li>
            <li><strong>Predicted Approve Rate</strong> - прогнозируемый approval rate на конец периода, %</li>
            <li><strong>Trend Slope</strong> - наклон тренда (скорость изменения approve rate, %/день)</li>
            <li><strong>R² (R-squared)</strong> - качество модели прогноза (0-1, выше = надежнее)</li>
            <li><strong>Avg Historical Approve Rate</strong> - средний исторический approval rate, %</li>
            <li><strong>Total Leads</strong> - всего лидов за период анализа</li>
            <li><strong>Total Approved</strong> - всего апрувнутых лидов (a_leads)</li>
        `,

        paramTranslations: {
            min_leads: 'Минимум лидов',
            history_days: 'Дней истории',
            forecast_days: 'Дней прогноза'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.forecasts) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const forecasts = results.data.forecasts;
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
                                    ${renderSortableHeader('current_approve_rate', 'Текущий Approve Rate', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('predicted_approve_rate', 'Прогноз (день ' + (period?.forecast_days || 7) + ')', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_slope', 'Тренд (%/день)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_label', 'Направление', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_leads', 'Всего лидов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('r_squared', 'R²', 'number', sortState.column, sortState.direction)}
                                    <th>Детали</th>
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                forecasts.forEach(forecast => {
                    const binomId = forecast.binom_id || forecast.campaign_id;

                    const trendIcon = forecast.trend === 'improving' ? '📈' :
                                     forecast.trend === 'declining' ? '📉' : '➡️';

                    const trendClass = forecast.trend === 'improving' ? 'text-success' :
                                      forecast.trend === 'declining' ? 'text-danger' : 'text-muted';

                    // Цвет для approve rate
                    const currentRateClass = forecast.current_approve_rate >= 50 ? 'text-success' :
                                            forecast.current_approve_rate >= 30 ? 'text-warning' :
                                            'text-danger';

                    const predictedRateClass = forecast.predicted_approve_rate >= 50 ? 'text-success' :
                                               forecast.predicted_approve_rate >= 30 ? 'text-warning' :
                                               'text-danger';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(forecast.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(forecast.group)}</small>
                            </td>
                            <td class="${currentRateClass}"><strong>${forecast.current_approve_rate.toFixed(2)}%</strong></td>
                            <td class="${predictedRateClass}"><strong>${forecast.predicted_approve_rate.toFixed(2)}%</strong></td>
                            <td class="${trendClass}">${forecast.trend_slope.toFixed(3)}</td>
                            <td class="${trendClass}">${trendIcon} ${forecast.trend_label}</td>
                            <td>${forecast.total_leads} <small class="text-muted">(${forecast.total_a_leads} apr.)</small></td>
                            <td>${forecast.r_squared.toFixed(3)}</td>
                            <td>
                                <button class="btn-mini approve-details-btn" data-campaign-id="${forecast.campaign_id}">
                                    Детали
                                </button>
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
                        <strong>Период прогноза:</strong> ${period.forecast_days || 7} дней вперед |
                        <strong>История:</strong> ${period.history_days || 14} дней |
                        <strong>Минимум лидов:</strong> ${params.min_leads || 10}
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, forecasts, (col, dir) => render(), sortState);

                // Подключаем обработчики для кнопок деталей
                const detailButtons = container.querySelectorAll('.approve-details-btn');
                detailButtons.forEach(button => {
                    button.addEventListener('click', function() {
                        const campaignId = parseInt(this.getAttribute('data-campaign-id'));
                        showApproveDetailsModal(campaignId);
                    });
                });
            };

            render();

            // Функция для показа деталей прогноза
            function showApproveDetailsModal(campaignId) {
                const forecast = forecasts.find(f => f.campaign_id === campaignId);
                if (!forecast) return;

                let details = `<div class="forecast-details">`;
                details += `<h4>Прогноз approval rate для: ${forecast.name}</h4>`;
                details += `<p><strong>Текущий Approve Rate:</strong> ${forecast.current_approve_rate.toFixed(2)}%</p>`;
                details += `<p><strong>Средний исторический Approve Rate:</strong> ${forecast.avg_historical_approve_rate.toFixed(2)}%</p>`;
                details += `<p><strong>Тренд:</strong> ${forecast.trend_label} (наклон: ${forecast.trend_slope.toFixed(3)}%/день)</p>`;
                details += `<p><strong>Точность модели (R²):</strong> ${forecast.r_squared.toFixed(3)}</p>`;
                details += `<p><strong>Статистика:</strong> ${forecast.total_leads} лидов, ${forecast.total_a_leads} апрувов</p>`;
                details += `<p><strong>Расход:</strong> ${formatCurrency(forecast.total_cost)} | <strong>Доход:</strong> ${formatCurrency(forecast.total_revenue)}</p>`;
                details += `<table class="mini-table">
                    <thead>
                        <tr>
                            <th>День</th>
                            <th>Прогноз Approve Rate</th>
                        </tr>
                    </thead>
                    <tbody>`;

                forecast.forecast.forEach(day => {
                    const rateClass = day.predicted_approve_rate >= 50 ? 'text-success' :
                                     day.predicted_approve_rate >= 30 ? 'text-warning' :
                                     'text-danger';
                    details += `
                        <tr>
                            <td>+${day.day}</td>
                            <td class="${rateClass}"><strong>${day.predicted_approve_rate.toFixed(2)}%</strong></td>
                        </tr>
                    `;
                });

                details += `</tbody></table></div>`;

                // Показываем модальное окно
                showModal('Детали прогноза approval rate', details);
            }
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(ApprovalRatePredictorModule);
    }
})();
