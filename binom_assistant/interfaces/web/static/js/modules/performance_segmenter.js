/**
 * Модуль: Сегменты эффективности
 * Разделение кампаний на топ/средние/слабые
 */
(function() {
    const PerformanceSegmenterModule = {
        id: 'performance_segmenter',

        translations: {
            total_campaigns: 'Всего кампаний',
            stars_count: 'Звезды (топ 25%)',
            performers_count: 'Перформеры (25-50%)',
            average_count: 'Середнячки (50-75%)',
            underperformers_count: 'Аутсайдеры (нижние 25%)'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за последние N дней</li>
                <li>Фильтрация кампаний:
                    <ul>
                        <li>Средний расход >= min_daily_spend (по умолчанию $1/день)</li>
                        <li>Минимум min_clicks кликов за период (по умолчанию 50)</li>
                    </ul>
                </li>
                <li>Расчет метрик для каждой кампании:
                    <ul>
                        <li>ROI = (revenue - cost) / cost * 100</li>
                        <li>CR = leads / clicks * 100</li>
                        <li>Profit = revenue - cost</li>
                    </ul>
                </li>
                <li>Вычисление квартилей (перцентилей):
                    <ul>
                        <li>Q1 (25й перцентиль)</li>
                        <li>Q2 (50й перцентиль, медиана)</li>
                        <li>Q3 (75й перцентиль)</li>
                    </ul>
                </li>
                <li>Сегментация кампаний по ROI:
                    <ul>
                        <li><strong>Звезды:</strong> ROI > Q3 (топ 25%)</li>
                        <li><strong>Перформеры:</strong> Q2 < ROI <= Q3 (25-50%)</li>
                        <li><strong>Середнячки:</strong> Q1 < ROI <= Q2 (50-75%)</li>
                        <li><strong>Аутсайдеры:</strong> ROI <= Q1 (нижние 25%)</li>
                    </ul>
                </li>
                <li>Сортировка кампаний внутри каждого сегмента по ROI (убывание)</li>
                <li>Расчет агрегированных метрик для каждого сегмента</li>
            </ol>
        `,

        metrics: `
            <li><strong>Total Campaigns</strong> - общее количество проанализированных кампаний</li>
            <li><strong>Q1, Q2, Q3</strong> - значения квартилей ROI</li>
            <li><strong>Segment Count</strong> - количество кампаний в сегменте</li>
            <li><strong>Total Cost</strong> - общий расход сегмента</li>
            <li><strong>Total Revenue</strong> - общий доход сегмента</li>
            <li><strong>Total Profit</strong> - общая прибыль сегмента</li>
            <li><strong>Avg ROI</strong> - средний ROI сегмента</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_daily_spend: 'Минимальный расход в день ($)',
            min_clicks: 'Минимум кликов'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.segments) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const segments = results.data.segments;
            const period = results.data.period || {};
            const params = results.data.params || {};
            const quartiles = results.data.quartiles || {};

            if (segments.length === 0) {
                container.innerHTML = '<p class="text-muted">Сегментов не найдено. Попробуйте изменить параметры.</p>';
                return;
            }

            let html = '';

            segments.forEach(segment => {
                if (segment.campaign_count === 0) {
                    return; // Пропускаем пустые сегменты
                }

                const profitClass = segment.total_profit >= 0 ? 'text-success' : 'text-danger';
                let segmentColor = '#1a1a1a';
                let borderColor = '#444';

                // Цвета для разных сегментов
                switch(segment.segment_id) {
                    case 'stars':
                        borderColor = 'rgba(75, 192, 192, 0.8)';
                        break;
                    case 'performers':
                        borderColor = 'rgba(54, 162, 235, 0.8)';
                        break;
                    case 'average':
                        borderColor = 'rgba(255, 206, 86, 0.8)';
                        break;
                    case 'underperformers':
                        borderColor = 'rgba(255, 99, 132, 0.8)';
                        break;
                }

                html += `
                    <div class="segment-block" style="margin: 20px 0; padding: 15px; border: 2px solid ${borderColor}; border-radius: 8px; background: ${segmentColor};">
                        <h4>${segment.segment_name}</h4>
                        <p class="text-muted">${segment.description}</p>
                        <div class="segment-summary" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0;">
                            <div>
                                <strong>Кампаний:</strong> ${segment.campaign_count}
                            </div>
                            <div>
                                <strong>Средний ROI:</strong> <span class="${segment.avg_roi >= 0 ? 'text-success' : 'text-danger'}">${segment.avg_roi.toFixed(1)}%</span>
                            </div>
                            <div>
                                <strong>Общий расход:</strong> ${formatCurrency(segment.total_cost)}
                            </div>
                            <div>
                                <strong>Общий доход:</strong> ${formatCurrency(segment.total_revenue)}
                            </div>
                            <div>
                                <strong>Прибыль:</strong> <span class="${profitClass}">${formatCurrency(segment.total_profit)}</span>
                            </div>
                        </div>
                        <div class="table-container" style="margin-top: 15px;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Кампания</th>
                                        <th>Клики</th>
                                        <th>Расход</th>
                                        <th>Доход</th>
                                        <th>Прибыль</th>
                                        <th>ROI (%)</th>
                                        <th>CR (%)</th>
                                        <th>Средн. расход/день</th>
                                        <th>Binom</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;

                segment.campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;
                    const roiClass = campaign.roi >= 0 ? 'text-success' : 'text-danger';
                    const profitClass = campaign.profit >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>${formatNumber(campaign.total_clicks)}</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
                            <td><span class="${profitClass}">${formatCurrency(campaign.profit)}</span></td>
                            <td><span class="${roiClass}">${campaign.roi.toFixed(1)}%</span></td>
                            <td>${campaign.cr.toFixed(2)}%</td>
                            <td>${formatCurrency(campaign.avg_daily_spend)}</td>
                            <td>${renderBinomLink(binomId)}</td>
                        </tr>
                    `;
                });

                html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            });

            // Info banner в конце
            html += `
                <div class="info-banner">
                    <strong>Период:</strong> ${period.days || 7} дней |
                    <strong>Мин. расход:</strong> ${params.min_daily_spend || 1}$/день |
                    <strong>Мин. кликов:</strong> ${params.min_clicks || 50} |
                    <strong>Квартили ROI:</strong> Q1=${quartiles.q1}% | Q2=${quartiles.q2}% | Q3=${quartiles.q3}%
                </div>
            `;

            container.innerHTML = html;
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(PerformanceSegmenterModule);
    }
})();
