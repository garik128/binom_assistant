/**
 * Модуль: Прогноз дохода
 * Прогнозирует revenue на следующие 7 дней на основе исторических данных
 */
(function() {
    const RevenueProjectionModule = {
        id: 'revenue_projection',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            increasing_count: 'С ростом',
            decreasing_count: 'С падением',
            stable_count: 'Стабильные',
            avg_r_squared: 'Средняя точность модели (R²)',
            total_projected_revenue: 'Общий прогнозируемый доход'
        },

        algorithm: `
            <ol>
                <li>Загрузка исторических данных revenue за последние 14-30 дней для каждой кампании</li>
                <li>Фильтрация кампаний с минимум $10 общего revenue за период</li>
                <li>Построение линейной регрессии для определения тренда revenue</li>
                <li>Экстраполяция тренда на 7 дней вперед</li>
                <li>Расчет доверительного интервала (80%) для прогноза</li>
                <li>Классификация трендов: рост (>$1/день), стабильность, падение (<-$1/день)</li>
                <li>Расчет суммарного прогнозируемого дохода за 7 дней</li>
                <li>Сортировка по убыванию прогнозируемого дохода - сначала самые доходные</li>
            </ol>
        `,

        metrics: `
            <li><strong>Current Daily Revenue</strong> - текущий дневной доход (последний день), $</li>
            <li><strong>Predicted Daily Revenue</strong> - прогнозируемый средний дневной доход, $</li>
            <li><strong>Total Projected Revenue</strong> - суммарный прогноз за 7 дней, $</li>
            <li><strong>Trend Slope</strong> - наклон тренда (скорость изменения revenue), $/день</li>
            <li><strong>R² (R-squared)</strong> - качество модели (0-1, выше = лучше)</li>
            <li><strong>Confidence Interval</strong> - доверительный интервал прогноза, $</li>
        `,

        paramTranslations: {
            history_days: 'Дней истории',
            forecast_days: 'Дней прогноза',
            min_revenue: 'Минимальный revenue',
            confidence_level: 'Уровень доверия'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.forecasts) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const forecasts = results.data.forecasts;
            const period = results.data.period || {};
            const summary = results.data.summary || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('current_daily_revenue', 'Текущий $/день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('predicted_daily_revenue', 'Прогноз $/день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_projected_revenue', 'Прогноз 7 дней ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_slope', 'Тренд ($/день)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_label', 'Направление', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('r_squared', 'R²', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_of_data', 'Дней данных', 'number', sortState.column, sortState.direction)}
                                    <th>Прогноз</th>
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                forecasts.forEach(forecast => {
                    const binomId = forecast.binom_id || forecast.campaign_id;

                    const trendClass = forecast.trend === 'increasing' ? 'text-success' :
                                      forecast.trend === 'decreasing' ? 'text-danger' : 'text-muted';

                    const trendArrow = forecast.trend === 'increasing' ? '↗' :
                                      forecast.trend === 'decreasing' ? '↘' : '→';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(forecast.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(forecast.group)}</small>
                            </td>
                            <td>${formatCurrency(forecast.current_daily_revenue)}</td>
                            <td>${formatCurrency(forecast.predicted_daily_revenue)}</td>
                            <td><strong>${formatCurrency(forecast.total_projected_revenue)}</strong></td>
                            <td class="${trendClass}">${forecast.trend_slope.toFixed(3)}</td>
                            <td class="${trendClass}">${trendArrow} ${forecast.trend_label}</td>
                            <td>${forecast.r_squared.toFixed(3)}</td>
                            <td>${forecast.days_of_data}</td>
                            <td>
                                <button class="btn-mini forecast-details-btn" data-campaign-id="${forecast.campaign_id}">
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
                        <strong>Общий прогноз:</strong> $${(summary.total_projected_revenue || 0).toFixed(2)}
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, forecasts, (col, dir) => render(), sortState);

                // Подключаем обработчики для кнопок деталей
                const detailButtons = container.querySelectorAll('.forecast-details-btn');
                detailButtons.forEach(button => {
                    button.addEventListener('click', function() {
                        const campaignId = parseInt(this.getAttribute('data-campaign-id'));
                        showForecastDetailsModal(campaignId);
                    });
                });
            };

            render();

            // Функция для показа деталей прогноза
            function showForecastDetailsModal(campaignId) {
                const forecast = forecasts.find(f => f.campaign_id === campaignId);
                if (!forecast) return;

                let details = `<div class="forecast-details">`;
                details += `<h4>Прогноз дохода для: ${forecast.name}</h4>`;
                details += `<p><strong>Текущий дневной revenue:</strong> $${forecast.current_daily_revenue.toFixed(2)}</p>`;
                details += `<p><strong>Средний исторический revenue:</strong> $${forecast.avg_historical_revenue.toFixed(2)}/день</p>`;
                details += `<p><strong>Прогнозируемый средний revenue:</strong> $${forecast.predicted_daily_revenue.toFixed(2)}/день</p>`;
                details += `<p><strong>Общий прогноз на ${period.forecast_days || 7} дней:</strong> $${forecast.total_projected_revenue.toFixed(2)}</p>`;
                details += `<p><strong>Тренд:</strong> ${forecast.trend_label} (наклон: $${forecast.trend_slope.toFixed(3)}/день)</p>`;
                details += `<p><strong>Точность модели (R²):</strong> ${forecast.r_squared.toFixed(3)}</p>`;
                details += `<p><strong>Стандартное отклонение:</strong> $${forecast.std_dev.toFixed(2)}</p>`;
                details += `<table class="mini-table">
                    <thead>
                        <tr>
                            <th>День</th>
                            <th>Прогноз Revenue</th>
                            <th>Нижняя граница</th>
                            <th>Верхняя граница</th>
                        </tr>
                    </thead>
                    <tbody>`;

                forecast.forecast.forEach(day => {
                    details += `
                        <tr>
                            <td>+${day.day}</td>
                            <td>$${day.predicted_revenue.toFixed(2)}</td>
                            <td>$${day.lower_bound.toFixed(2)}</td>
                            <td>$${day.upper_bound.toFixed(2)}</td>
                        </tr>
                    `;
                });

                // Добавляем итоговую строку
                const totalPredicted = forecast.forecast.reduce((sum, day) => sum + day.predicted_revenue, 0);
                details += `
                    <tr style="font-weight: bold; border-top: 2px solid #444;">
                        <td>ИТОГО</td>
                        <td>$${totalPredicted.toFixed(2)}</td>
                        <td colspan="2"></td>
                    </tr>
                `;

                details += `</tbody></table>`;
                details += `<p class="text-muted" style="margin-top: 10px;"><small>Доверительный интервал: ${results.data?.params?.confidence_level || 80}%</small></p>`;
                details += `</div>`;

                // Показываем модальное окно (функция showModal из _utils.js)
                showModal('Детали прогноза дохода', details);
            }
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(RevenueProjectionModule);
    }
})();
