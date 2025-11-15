/**
 * Модуль: Цикл оффера (Offer Lifecycle Tracker)
 * Определяет стадию жизни офферов
 */
(function() {
    const OfferLifecycleTrackerModule = {
        id: 'offer_lifecycle_tracker',

        translations: {
            offer_name: 'Оффер',
            stage: 'Стадия',
            days_active: 'Дней активности',
            roi: 'ROI (%)',
            avg_cr: 'Средний CR (%)',
            roi_trend: 'Тренд ROI',
            revenue_trend: 'Тренд дохода',
            recommendation: 'Рекомендация',
            total_cost: 'Расход ($)',
            total_revenue: 'Доход ($)',
            total_leads: 'Лиды',
            total_a_leads: 'Апруве лиды',
            total_clicks: 'Клики',
            geo: 'Гео',
            total_offers: 'Всего офферов',
            new_offers: 'Новые',
            growing_offers: 'Растущие',
            mature_offers: 'Зрелые',
            declining_offers: 'Умирающие',
            dead_offers: 'Мертвые',
            avg_roi: 'Средний ROI',
            total_leads_portfolio: 'Всего лидов'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Группировка кампаний по офферам (группам)</li>
                <li>Фильтрация офферов с минимальной активностью</li>
                <li>Определение стадии жизненного цикла:
                    <ol>
                        <li><strong>Новый оффер</strong>: < 7 дней активности
                            <ul>
                                <li>Только что начали работу</li>
                                <li>Недостаточная статистика</li>
                            </ul>
                        </li>
                        <li><strong>Растущий оффер</strong>: ROI и объемы растут
                            <ul>
                                <li>Положительный тренд ROI</li>
                                <li>Растущие объемы доходов</li>
                            </ul>
                        </li>
                        <li><strong>Зрелый оффер</strong>: Стабильные показатели > 14 дней
                            <ul>
                                <li>Стабильный ROI > 0</li>
                                <li>Долгая история</li>
                                <li>Хороший результат</li>
                            </ul>
                        </li>
                        <li><strong>Умирающий оффер</strong>: Снижение CR и ROI > 7 дней
                            <ul>
                                <li>Отрицательный тренд ROI</li>
                                <li>Падающие объемы</li>
                                <li>Требует внимания</li>
                            </ul>
                        </li>
                        <li><strong>Мертвый оффер</strong>: ROI < 0 более 5 дней
                            <ul>
                                <li>Постоянные убытки</li>
                                <li>Рекомендуется закрытие</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет трендов ROI и дохода (сравнение половин периода)</li>
                <li>Генерация рекомендаций для каждого оффера</li>
            </ol>
        `,

        metrics: `
            <li><strong>Offer</strong> - имя/группа оффера</li>
            <li><strong>Stage</strong> - текущая стадия жизненного цикла (new/growing/mature/declining/dead)</li>
            <li><strong>Days Active</strong> - количество дней с активностью</li>
            <li><strong>ROI (%)</strong> - return on investment по офферу</li>
            <li><strong>Average CR (%)</strong> - средний conversion rate</li>
            <li><strong>ROI Trend</strong> - тренд ROI (growing/stable/declining)</li>
            <li><strong>Revenue Trend</strong> - тренд доходов (growing/stable/declining)</li>
            <li><strong>Recommendation</strong> - действие, рекомендуемое для оффера</li>
            <li><strong>Total Cost</strong> - общий расход по офферу ($)</li>
            <li><strong>Total Revenue</strong> - общий доход по офферу ($)</li>
            <li><strong>Total Leads</strong> - количество лидов</li>
            <li><strong>Campaigns Count</strong> - количество кампаний по офферу</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_days_active: 'Минимум дней активности',
            min_cost: 'Минимальный расход ($)',
            new_stage_days: 'Дней для стадии "Новый"',
            mature_stage_days: 'Дней для стадии "Зрелый"',
            dying_stage_days: 'Дней для стадии "Умирающий"',
            dead_stage_days: 'Дней для анализа тренда'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.offers) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const offers = data.offers || [];
            const summary = data.summary || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';

                // Таблица офферов (summary отрисовывается отдельно в resultsSummary)
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    ${renderSortableHeader('offer_name', 'Оффер', 'text', sortState.column, sortState.direction)}
                                    <th>Гео</th>
                                    ${renderSortableHeader('stage', 'Стадия', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_active', 'Дней активен', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi', 'ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_cr', 'CR (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_leads', 'Лиды', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_a_leads', 'Апрув', 'number', sortState.column, sortState.direction)}
                                    <th>Тренд ROI</th>
                                    <th>Рекомендация</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                offers.forEach((offer) => {
                    const stageInfo = this._getStageInfo(offer.stage);
                    const trendIcon = {
                        'growing': '▲',
                        'stable': '▬',
                        'declining': '▼'
                    };

                    const trendClass = {
                        'growing': 'text-success',
                        'stable': 'text-muted',
                        'declining': 'text-danger'
                    };

                    const offerId = offer.offer_id || 'N/A';
                    const geoText = offer.geo || '-';

                    html += `
                        <tr>
                            <td>
                                <strong>[${offerId}] ${this._escapeHtml(offer.offer_name || 'Unknown')}</strong>
                            </td>
                            <td>${geoText}</td>
                            <td>
                                <span class="stage-badge" style="background: ${stageInfo.color}; color: white; padding: 4px 8px; border-radius: 4px;">
                                    ${stageInfo.label}
                                </span>
                            </td>
                            <td>${offer.days_active}</td>
                            <td class="${offer.roi >= 0 ? 'text-success' : 'text-danger'}">${offer.roi >= 0 ? '+' : ''}${offer.roi.toFixed(1)}%</td>
                            <td>${offer.avg_cr.toFixed(2)}%</td>
                            <td>${formatCurrency(offer.total_cost)}</td>
                            <td class="text-success">${formatCurrency(offer.total_revenue)}</td>
                            <td>${offer.total_leads}</td>
                            <td>${offer.total_a_leads}</td>
                            <td class="${trendClass[offer.roi_trend] || 'text-muted'}">
                                ${trendIcon[offer.roi_trend] || '?'} ${this._getTrendLabel(offer.roi_trend)}
                            </td>
                            <td>
                                <small>${this._escapeHtml(offer.recommendation)}</small>
                            </td>
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
                attachTableSortHandlers(container, offers, (col, dir) => render(), sortState);
            };

            render();
        },

        _getStageInfo: function(stage) {
            const stageInfo = {
                'new': {
                    label: 'Новый',
                    color: '#17a2b8'
                },
                'growing': {
                    label: 'Растущий',
                    color: '#28a745'
                },
                'mature': {
                    label: 'Зрелый',
                    color: '#0d6efd'
                },
                'declining': {
                    label: 'Умирающий',
                    color: '#ffc107'
                },
                'dead': {
                    label: 'Мертвый',
                    color: '#dc3545'
                }
            };
            return stageInfo[stage] || stageInfo['new'];
        },

        _getTrendLabel: function(trend) {
            const labels = {
                'growing': 'Растет',
                'stable': 'Стабильно',
                'declining': 'Падает'
            };
            return labels[trend] || trend;
        },

        _escapeHtml: function(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        renderCharts: function(results, chartsContainer) {
            if (!results.data) return;

            const data = results.data;
            const offers = data.offers || [];
            const summary = data.summary || {};

            if (!results.charts || results.charts.length === 0) return;

            // Очищаем контейнер
            chartsContainer.innerHTML = '';

            results.charts.forEach(chartDef => {
                const chartContainer = document.createElement('div');
                chartContainer.className = 'chart-container';
                chartContainer.innerHTML = `<canvas id="${chartDef.id}"></canvas>`;
                chartsContainer.appendChild(chartContainer);

                setTimeout(() => {
                    const canvas = document.getElementById(chartDef.id);
                    if (canvas && window.Chart) {
                        try {
                            new window.Chart(canvas, {
                                type: chartDef.type,
                                data: chartDef.data,
                                options: chartDef.options || {}
                            });
                        } catch (e) {
                            console.error(`Error rendering chart ${chartDef.id}:`, e);
                        }
                    }
                }, 0);
            });
        },

        renderStats: function(results, statsContainer) {
            if (!results.data) return;

            const summary = results.data.summary || {};
            const offers = results.data.offers || [];

            let html = `
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-label">Новые офферы</div>
                        <div class="stat-value">
                            ${summary.new_offers || 0}
                        </div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Растущие офферы</div>
                        <div class="stat-value text-success">
                            ${summary.growing_offers || 0}
                        </div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Зрелые офферы</div>
                        <div class="stat-value">
                            ${summary.mature_offers || 0}
                        </div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Умирающие офферы</div>
                        <div class="stat-value">
                            ${summary.declining_offers || 0}
                        </div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Мертвые офферы</div>
                        <div class="stat-value text-danger">
                            ${summary.dead_offers || 0}
                        </div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Средний ROI</div>
                        <div class="stat-value ${(summary.avg_roi || 0) >= 0 ? 'text-success' : 'text-danger'}">
                            ${(summary.avg_roi || 0).toFixed(1)}%
                        </div>
                    </div>
                </div>
            `;

            statsContainer.innerHTML = html;
        }
    };

    // Регистрация модуля в registry
    if (window.ModuleRegistry) {
        window.ModuleRegistry.register(OfferLifecycleTrackerModule);
    }
})();
