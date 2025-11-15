/**
 * Модуль: Умное объединение
 * Объединение похожих малобюджетных кампаний
 */
(function() {
    const SmartConsolidatorModule = {
        id: 'smart_consolidator',

        translations: {
            total_clusters: 'Всего кластеров',
            total_campaigns: 'Кампаний в кластерах',
            total_small_campaigns: 'Малобюджетных кампаний',
            avg_cluster_size: 'Средний размер кластера'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных за последние N дней</li>
                <li>Фильтрация малобюджетных кампаний:
                    <ul>
                        <li>Средний расход <= max_daily_spend (по умолчанию $2/день)</li>
                        <li>Минимум min_total_clicks кликов за период (по умолчанию 50)</li>
                    </ul>
                </li>
                <li>Расчет метрик для каждой кампании:
                    <ul>
                        <li>ROI = (revenue - cost) / cost * 100</li>
                        <li>CR = leads / clicks * 100</li>
                    </ul>
                </li>
                <li>Нормализация метрик в диапазон [0, 1]</li>
                <li>Создание векторов признаков: [normalized_roi, normalized_cr, normalized_cost]</li>
                <li>Кластеризация методом ближайшего соседа:
                    <ul>
                        <li>Вычисление косинусного расстояния между векторами</li>
                        <li>Объединение кампаний с similarity >= similarity_threshold</li>
                    </ul>
                </li>
                <li>Формирование кластеров:
                    <ul>
                        <li>Минимум min_campaigns_per_cluster кампаний в кластере</li>
                        <li>Расчет средних метрик кластера</li>
                    </ul>
                </li>
                <li>Сортировка кластеров по среднему ROI (убывание)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Total Clusters</strong> - количество найденных кластеров</li>
            <li><strong>Total Campaigns</strong> - общее количество кампаний в кластерах</li>
            <li><strong>Total Small Campaigns</strong> - всего малобюджетных кампаний</li>
            <li><strong>Avg Cluster Size</strong> - среднее количество кампаний в кластере</li>
            <li><strong>Campaign Count</strong> - количество кампаний в кластере</li>
            <li><strong>Avg ROI</strong> - средний ROI кластера</li>
            <li><strong>Avg CR</strong> - средний CR кластера</li>
            <li><strong>Total Cost</strong> - общий расход кластера</li>
            <li><strong>Total Revenue</strong> - общий доход кластера</li>
            <li><strong>Косинусное расстояние</strong> - мера схожести векторов признаков (1 = полностью схожие)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            max_daily_spend: 'Макс. расход в день ($)',
            min_campaigns_per_cluster: 'Минимум кампаний в кластере',
            similarity_threshold: 'Порог схожести',
            min_total_clicks: 'Минимум кликов'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.clusters) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const clusters = results.data.clusters;
            const period = results.data.period || {};
            const params = results.data.params || {};

            if (clusters.length === 0) {
                container.innerHTML = '<p class="text-muted">Кластеров не найдено. Попробуйте изменить параметры.</p>';
                return;
            }

            let html = '';

            clusters.forEach(cluster => {
                const profit = cluster.total_revenue - cluster.total_cost;
                const profitClass = profit >= 0 ? 'text-success' : 'text-danger';

                html += `
                    <div class="cluster-block" style="margin: 20px 0; padding: 15px; border: 1px solid #444; border-radius: 8px; background: #1a1a1a;">
                        <h4>Кластер ${cluster.cluster_id}</h4>
                        <div class="cluster-summary" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0;">
                            <div>
                                <strong>Кампаний:</strong> ${cluster.campaign_count}
                            </div>
                            <div>
                                <strong>Средний ROI:</strong> <span class="${cluster.avg_roi >= 0 ? 'text-success' : 'text-danger'}">${cluster.avg_roi.toFixed(1)}%</span>
                            </div>
                            <div>
                                <strong>Средний CR:</strong> ${cluster.avg_cr.toFixed(2)}%
                            </div>
                            <div>
                                <strong>Общий расход:</strong> ${formatCurrency(cluster.total_cost)}
                            </div>
                            <div>
                                <strong>Общий доход:</strong> ${formatCurrency(cluster.total_revenue)}
                            </div>
                            <div>
                                <strong>Прибыль:</strong> <span class="${profitClass}">${formatCurrency(profit)}</span>
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
                                        <th>ROI (%)</th>
                                        <th>CR (%)</th>
                                        <th>Средн. расход/день</th>
                                        <th>Binom</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;

                cluster.campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;
                    const roiClass = campaign.roi >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>${formatNumber(campaign.total_clicks)}</td>
                            <td>${formatCurrency(campaign.total_cost)}</td>
                            <td>${formatCurrency(campaign.total_revenue)}</td>
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
                    <strong>Макс. расход:</strong> ${params.max_daily_spend || 2}$/день |
                    <strong>Порог схожести:</strong> ${Math.round((params.similarity_threshold || 0.8) * 100)}% |
                    <strong>Мин. кликов:</strong> ${params.min_total_clicks || 50}
                </div>
            `;

            container.innerHTML = html;
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SmartConsolidatorModule);
    }
})();
