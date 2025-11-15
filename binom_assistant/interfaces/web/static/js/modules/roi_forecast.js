/**
 * Модуль: Прогноз окупаемости
 * Прогнозирует ROI на 3-7 дней вперед на основе исторических данных
 */
(function() {
    const ROIForecastModule = {
        id: 'roi_forecast',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            improving_count: 'С улучшением',
            declining_count: 'С ухудшением',
            stable_count: 'Стабильные',
            avg_r_squared: 'Средняя точность модели (R²)'
        },

        algorithm: `
            <ol>
                <li>Загрузка исторических данных ROI за последние 30 дней для каждой кампании</li>
                <li>Фильтрация кампаний с минимум 7 днями активности и расходом > $1/день</li>
                <li>Построение линейной регрессии для определения тренда ROI</li>
                <li>Экстраполяция тренда на 3-7 дней вперед</li>
                <li>Расчет доверительного интервала (80%) для прогноза</li>
                <li>Классификация трендов: улучшение, стабильность, ухудшение</li>
                <li>Генерация алертов для кампаний с прогнозом ухудшения</li>
            </ol>
        `,

        metrics: `
            <li><strong>Predicted ROI</strong> - прогнозируемый ROI, %</li>
            <li><strong>Trend Slope</strong> - наклон тренда (скорость изменения ROI)</li>
            <li><strong>R² (R-squared)</strong> - качество модели (0-1, выше = лучше)</li>
            <li><strong>Confidence Interval</strong> - доверительный интервал прогноза</li>
            <li><strong>Historical ROI</strong> - средний исторический ROI, %</li>
            <li><strong>Current ROI</strong> - текущий ROI (последний день), %</li>
        `,

        paramTranslations: {
            history_days: 'Дней истории',
            forecast_days: 'Дней прогноза',
            min_history_days: 'Минимум дней с данными',
            min_daily_spend: 'Минимальный расход/день',
            confidence_level: 'Уровень доверия'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.forecasts) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const forecasts = results.data.forecasts;
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
                                    ${renderSortableHeader('current_roi', 'Текущий ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('predicted_roi', 'Прогноз (день ' + (period.forecast_days || 7) + ')', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_slope', 'Тренд', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('trend_label', 'Направление', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('r_squared', 'R²', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_daily_spend', 'Расход/день', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_of_data', 'Дней данных', 'number', sortState.column, sortState.direction)}
                                    <th>Прогноз</th>
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                forecasts.forEach(forecast => {
                    const binomId = forecast.binom_id || forecast.campaign_id;
                    const lastForecast = forecast.forecast && forecast.forecast.length > 0
                        ? forecast.forecast[forecast.forecast.length - 1]
                        : { predicted_roi: 0, lower_bound: 0, upper_bound: 0 };

                    // Определяем predicted_roi для сортировки
                    forecast.predicted_roi = lastForecast.predicted_roi;

                    const trendIcon = forecast.trend === 'improving' ? '📈' :
                                     forecast.trend === 'declining' ? '📉' : '➡️';

                    const trendClass = forecast.trend === 'improving' ? 'text-success' :
                                      forecast.trend === 'declining' ? 'text-danger' : 'text-muted';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(forecast.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(forecast.group)}</small>
                            </td>
                            <td>${formatROI(forecast.current_roi)}</td>
                            <td>${formatROI(lastForecast.predicted_roi)}</td>
                            <td class="${trendClass}">${forecast.trend_slope.toFixed(3)}</td>
                            <td class="${trendClass}">${trendIcon} ${forecast.trend_label}</td>
                            <td>${forecast.r_squared.toFixed(3)}</td>
                            <td>${formatCurrency(forecast.avg_daily_spend)}/день</td>
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
                        <strong>История:</strong> ${period.history_days || 30} дней
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
                details += `<h4>Прогноз для: ${forecast.name}</h4>`;
                details += `<p><strong>Текущий ROI:</strong> ${forecast.current_roi.toFixed(2)}%</p>`;
                details += `<p><strong>Средний исторический ROI:</strong> ${forecast.avg_historical_roi.toFixed(2)}%</p>`;
                details += `<p><strong>Тренд:</strong> ${forecast.trend_label} (наклон: ${forecast.trend_slope.toFixed(3)})</p>`;
                details += `<p><strong>Точность модели (R²):</strong> ${forecast.r_squared.toFixed(3)}</p>`;
                details += `<table class="mini-table">
                    <thead>
                        <tr>
                            <th>День</th>
                            <th>Прогноз ROI</th>
                            <th>Нижняя граница</th>
                            <th>Верхняя граница</th>
                        </tr>
                    </thead>
                    <tbody>`;

                forecast.forecast.forEach(day => {
                    details += `
                        <tr>
                            <td>+${day.day}</td>
                            <td>${day.predicted_roi.toFixed(2)}%</td>
                            <td>${day.lower_bound.toFixed(2)}%</td>
                            <td>${day.upper_bound.toFixed(2)}%</td>
                        </tr>
                    `;
                });

                details += `</tbody></table></div>`;

                // Показываем модальное окно
                showModal('Детали прогноза', details);
            }
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(ROIForecastModule);
    }
})();
