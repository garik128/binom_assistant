/**
 * Модуль: Общая динамика портфеля (Total Performance Tracker)
 * Отслеживает динамику общих показателей портфеля
 */
(function() {
    const TotalPerformanceTrackerModule = {
        id: 'total_performance_tracker',

        translations: {
            current_period_cost: 'Расход текущий период',
            current_period_revenue: 'Доход текущий период',
            current_period_profit: 'Прибыль текущий период',
            current_period_roi: 'ROI текущий период',
            current_period_clicks: 'Клики текущий период',
            current_period_leads: 'Лиды текущий период',
            previous_period_cost: 'Расход предыдущий период',
            previous_period_revenue: 'Доход предыдущий период',
            previous_period_profit: 'Прибыль предыдущий период',
            previous_period_roi: 'ROI предыдущий период',
            cost_change: 'Изменение расхода',
            revenue_change: 'Изменение дохода',
            profit_change: 'Изменение прибыли',
            roi_change: 'Изменение ROI',
            clicks_change: 'Изменение кликов',
            leads_change: 'Изменение лидов',
            trend: 'Тренд',
            total_cost: 'Общий расход',
            total_revenue: 'Общий доход',
            total_profit: 'Общая прибыль',
            roi: 'ROI',
            clicks: 'Клики',
            leads: 'Лиды',
            approved_leads: 'Одобренные лиды'
        },

        algorithm: `
            <ol>
                <li>Загружаются агрегированные метрики портфеля за выбранный период (по умолчанию 7 дней)</li>
                <li>Загружаются аналогичные данные за предыдущий период равной длины для сравнения</li>
                <li>Рассчитываются ключевые метрики текущего периода: общий расход, доход, прибыль, ROI, клики, лиды</li>
                <li>Рассчитываются аналогичные метрики предыдущего периода</li>
                <li>Определяются процентные изменения по каждой метрике между периодами</li>
                <li>Рассчитывается общий тренд на основе трех ключевых метрик (доход, прибыль, ROI)</li>
                <li>Тренд классифицируется как: improving (растущий), stable (стабильный), declining (падающий)</li>
                <li>Формируются алерты о тренде, ROI, расходах и прибыли</li>
            </ol>
        `,

        metrics: `
            <li><strong>Текущий период</strong> - все метрики за выбранный период анализа</li>
            <li><strong>Общий расход (Cost)</strong> - сумма расходов всех кампаний за период, $</li>
            <li><strong>Общий доход (Revenue)</strong> - сумма доходов всех кампаний за период, $</li>
            <li><strong>Общая прибыль (Profit)</strong> - разница между доходом и расходом, $</li>
            <li><strong>ROI портфеля</strong> - (Доход - Расход) / Расход * 100, %</li>
            <li><strong>Общие клики</strong> - сумма кликов всех кампаний за период</li>
            <li><strong>Общие лиды</strong> - сумма лидов всех кампаний за период</li>
            <li><strong>Предыдущий период</strong> - аналогичные метрики за предыдущий период</li>
            <li><strong>Изменения</strong> - процентные (%) изменения между периодами</li>
            <li><strong>Тренд</strong> - общая динамика: improving (улучшается), stable (стабилен), declining (ухудшается)</li>
        `,

        paramTranslations: {
            days: 'Период анализа',
            min_change_threshold: 'Порог изменения (%)',
            high_roi_threshold: 'Порог высокого ROI (%)',
            high_cost_change_threshold: 'Порог изменения расходов (%)'
        },

        /**
         * Отрисовка главного контента для total_performance_tracker
         */
        renderTable: function(results, container) {
            if (!results.data) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const current = results.data.current_period || {};
            const previous = results.data.previous_period || {};
            const changes = results.data.changes || {};
            const trend = results.data.trend || 'stable';
            const period = results.data.period || {};

            // Определяем цвета для тренда
            const trendColors = {
                'improving': '#28a745',
                'stable': '#6c757d',
                'declining': '#dc3545'
            };

            const trendLabels = {
                'improving': 'Улучшается',
                'stable': 'Стабилен',
                'declining': 'Ухудшается'
            };

            // Вспомогательная функция для форматирования изменений
            const formatChange = (value) => {
                if (value > 0) return `<span class="text-success">+${value.toFixed(1)}%</span>`;
                if (value < 0) return `<span class="text-danger">${value.toFixed(1)}%</span>`;
                return `<span class="text-muted">${value.toFixed(1)}%</span>`;
            };

            // Вспомогательная функция для форматирования ROI изменения
            const formatROIChange = (value) => {
                if (value > 0) return `<span class="text-success">+${value.toFixed(1)}%</span>`;
                if (value < 0) return `<span class="text-danger">${value.toFixed(1)}%</span>`;
                return `<span class="text-muted">${value.toFixed(1)}%</span>`;
            };

            // Создаем displaySummary из current_period для стандартной сетки
            const displaySummary = {
                total_cost: current.total_cost || 0,
                total_revenue: current.total_revenue || 0,
                total_profit: current.total_profit || 0,
                roi: current.total_roi || 0,
                clicks: current.total_clicks || 0,
                leads: current.total_leads || 0,
                trend: trend
            };

            let html = `
                <div class="performance-tracker-main">
                    <!-- Тренд индикатор -->
                    <div class="trend-indicator-banner" style="background: rgba(${
                        trend === 'improving' ? '40, 167, 69' :
                        trend === 'declining' ? '220, 53, 69' :
                        '108, 117, 125'
                    }, 0.1); border-left: 4px solid ${trendColors[trend]}; padding: 16px; margin-bottom: 20px; border-radius: 4px;">
                        <div style="display: flex; align-items: center; gap: 16px;">
                            <div>
                                <div class="text-muted" style="font-size: 12px; text-transform: uppercase; margin-bottom: 4px;">Общий тренд</div>
                                <div style="font-size: 20px; font-weight: bold; color: ${trendColors[trend]};">
                                    ${trendLabels[trend]}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Главные метрики в стандартной summary-grid -->
                    <div class="summary-grid">
                        <div class="summary-card">
                            <div class="summary-label">ROI</div>
                            <div class="summary-value ${displaySummary.roi >= 0 ? 'text-success' : 'text-danger'}">
                                ${displaySummary.roi.toFixed(1)}%
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.roi_change || 0)}
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-label">Доход</div>
                            <div class="summary-value text-success">
                                ${formatCurrency(displaySummary.total_revenue)}
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.revenue_change || 0)}
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-label">Расход</div>
                            <div class="summary-value">
                                ${formatCurrency(displaySummary.total_cost)}
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.cost_change || 0)}
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-label">Прибыль</div>
                            <div class="summary-value ${displaySummary.total_profit >= 0 ? 'text-success' : 'text-danger'}">
                                ${formatCurrency(displaySummary.total_profit)}
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.profit_change || 0)}
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-label">Клики</div>
                            <div class="summary-value">
                                ${displaySummary.clicks}
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.clicks_change || 0)}
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-label">Лиды</div>
                            <div class="summary-value">
                                ${displaySummary.leads}
                            </div>
                            <div class="text-muted" style="font-size: 11px; margin-top: 4px;">
                                ${formatChange(changes.leads_change || 0)}
                            </div>
                        </div>
                    </div>

                    <!-- Сравнительная таблица -->
                    <div class="comparison-table">
                        <h3>Сравнение периодов</h3>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Метрика</th>
                                        <th>Текущий период</th>
                                        <th>Предыдущий период</th>
                                        <th>Изменение</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><strong>Расход</strong></td>
                                        <td>${formatCurrency(current.total_cost || 0)}</td>
                                        <td>${formatCurrency(previous.total_cost || 0)}</td>
                                        <td>${formatChange(changes.cost_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Доход</strong></td>
                                        <td>${formatCurrency(current.total_revenue || 0)}</td>
                                        <td>${formatCurrency(previous.total_revenue || 0)}</td>
                                        <td>${formatChange(changes.revenue_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Прибыль</strong></td>
                                        <td class="${current.total_profit >= 0 ? 'text-success' : 'text-danger'}" style="font-weight: bold;">
                                            ${formatCurrency(current.total_profit || 0)}
                                        </td>
                                        <td class="${previous.total_profit >= 0 ? 'text-success' : 'text-danger'}" style="font-weight: bold;">
                                            ${formatCurrency(previous.total_profit || 0)}
                                        </td>
                                        <td>${formatChange(changes.profit_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>ROI</strong></td>
                                        <td>${current.total_roi !== undefined ? current.total_roi.toFixed(1) : 0}%</td>
                                        <td>${previous.total_roi !== undefined ? previous.total_roi.toFixed(1) : 0}%</td>
                                        <td>${formatROIChange(changes.roi_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Клики</strong></td>
                                        <td>${current.total_clicks !== undefined ? current.total_clicks : 0}</td>
                                        <td>${previous.total_clicks !== undefined ? previous.total_clicks : 0}</td>
                                        <td>${formatChange(changes.clicks_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Лиды</strong></td>
                                        <td>${current.total_leads !== undefined ? current.total_leads : 0}</td>
                                        <td>${previous.total_leads !== undefined ? previous.total_leads : 0}</td>
                                        <td>${formatChange(changes.leads_change || 0)}</td>
                                    </tr>
                                    <tr>
                                        <td><strong>Одобренные лиды</strong></td>
                                        <td>${current.total_a_leads !== undefined ? current.total_a_leads : 0}</td>
                                        <td>${previous.total_a_leads !== undefined ? previous.total_a_leads : 0}</td>
                                        <td>${formatChange(changes.a_leads_change || 0)}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Info banner -->
                    <div class="info-banner">
                        <strong>Период:</strong> ${period.days || 7} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
                    </div>
                </div>
            `;

            container.innerHTML = html;
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(TotalPerformanceTrackerModule);
    }
})();
