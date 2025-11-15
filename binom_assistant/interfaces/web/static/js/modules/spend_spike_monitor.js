/**
 * Модуль: Монитор всплесков расходов
 * Находит аномальные всплески расходов в кампаниях
 */
(function() {
    const SpendSpikeMonitorModule = {
        id: 'spend_spike_monitor',

        translations: {
            total_extra_spend: 'Излишне потрачено',
            avg_spike_ratio: 'Среднее превышение'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика за последние N+1 дней (базовый период + вчерашний день)</li>
                <li>Для каждой кампании рассчитывается среднее расходов за базовый период</li>
                <li>Вычисляется стандартное отклонение (σ) расходов за базовый период</li>
                <li>Определяется пороговое значение: среднее + N*σ (где N - множитель сигмы)</li>
                <li>Сравнивается расход за вчерашний день с пороговым значением</li>
                <li>Проверяется кратность превышения (spike_threshold, например 1.5x = превышение в 1.5 раза)</li>
                <li>Проверяется нет ли пропорционального роста конверсий (CR)</li>
                <li>Если все условия выполнены - фиксируется всплеск расходов</li>
                <li>Определяется критичность на основе кратности превышения порога</li>
            </ol>
        `,

        metrics: `
            <li><strong>Среднее расходов</strong> - среднее значение расходов за базовый период (7 дней), $</li>
            <li><strong>Стандартное отклонение (σ)</strong> - мера разброса расходов относительно среднего</li>
            <li><strong>Порог всплеска</strong> - среднее + N*σ, пороговое значение для детекции аномалий</li>
            <li><strong>Расход последнего дня</strong> - фактический расход за текущий день, $</li>
            <li><strong>Абсолютное увеличение</strong> - разница между последним днем и средним, $</li>
            <li><strong>Коэффициент всплеска</strong> - кратность превышения порогового значения</li>
            <li><strong>CR (Conversion Rate)</strong> - конверсия в лиды для проверки пропорционального роста, %</li>
            <li><strong>Базовый период</strong> - количество дней для расчета статистики (по умолчанию 7)</li>
            <li><strong>Множитель σ (сигма)</strong> - регулирует чувствительность детектора аномалий:
                <ul style="margin: 5px 0 0 20px; font-size: 0.9em;">
                    <li><strong>1-2</strong>: Высокая чувствительность - найдет даже небольшие отклонения от нормы (может быть много ложных срабатываний)</li>
                    <li><strong>3</strong>: Стандартная чувствительность - находит статистически значимые аномалии (по умолчанию)</li>
                    <li><strong>4-5</strong>: Низкая чувствительность - только очень крупные и явные всплески расходов</li>
                </ul>
            </li>
        `,

        paramTranslations: {
            base_days: 'Базовый период',
            spike_threshold: 'Порог всплеска',
            sigma_multiplier: 'Множитель σ (сигма)',
            min_base_spend: 'Мин. средний расход',
            cr_growth_threshold: 'Порог роста CR'
        },

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
                                    ${renderSortableHeader('last_day_cost', 'Расход вчера', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('mean_cost', 'Средний расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('spike_ratio', 'Коэфф. всплеска', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('absolute_increase', 'Превышение', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('last_day_cr', 'CR вчера', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('mean_cr', 'Средний CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td class="text-danger"><strong>${formatCurrency(campaign.last_day_cost)}</strong></td>
                            <td>${formatCurrency(campaign.mean_cost)}</td>
                            <td class="text-danger"><strong>${campaign.spike_ratio.toFixed(2)}x</strong></td>
                            <td class="text-danger">+${formatCurrency(campaign.absolute_increase)}</td>
                            <td>${campaign.last_day_cr.toFixed(2)}%</td>
                            <td>${campaign.mean_cr.toFixed(2)}%</td>
                            <td>${formatROI(campaign.avg_roi)}</td>
                            <td>${formatSeverity(campaign.severity)}</td>
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
        ModuleRegistry.register(SpendSpikeMonitorModule);
    }
})();
