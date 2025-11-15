/**
 * Модуль: Колебания метрик (Volatility Calculator)
 * Расчет волатильности ключевых метрик кампаний
 */
(function() {
    const VolatilityCalculatorModule = {
        id: 'volatility_calculator',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_low: 'Низкая волатильность (<20%)',
            total_medium: 'Средняя волатильность (20-50%)',
            total_high: 'Высокая волатильность (50-150%)',
            total_extreme: 'Экстремальная волатильность (>150%)',
            avg_volatility: 'Средняя волатильность портфеля',
            most_stable_volatility: 'Минимальная волатильность',
            most_volatile_volatility: 'Максимальная волатильность'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за указанный период (по умолчанию 14 дней)</li>
                <li>Для каждого дня вычисляются ключевые метрики: ROI, CR, approve rate</li>
                <li>Рассчитывается стандартное отклонение (σ) для каждой метрики за период</li>
                <li>Вычисляется коэффициент вариации (CV = σ/μ × 100) для нормализации</li>
                <li>Для CPL кампаний учитываются только ROI и CR (approve rate не применим)</li>
                <li>CV ограничен максимум 500% для предотвращения экстремальных значений при малых средних</li>
                <li>Рассчитывается общий индекс волатильности как среднее CV всех метрик</li>
                <li>Классификация: низкая (<20%), средняя (20-50%), высокая (50-150%), экстремальная (>150%)</li>
                <li>Фильтруются кампании с минимальным расходом ($1/день) и количеством дней с данными (7 дней)</li>
                <li>Формируются алерты для кампаний с экстремальной волатильностью (>150%)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Общая волатильность</strong> - средний коэффициент вариации всех метрик, показывает общую нестабильность, %</li>
            <li><strong>ROI σ (стандартное отклонение)</strong> - разброс значений ROI относительно среднего, %</li>
            <li><strong>ROI CV (коэффициент вариации)</strong> - нормализованная волатильность ROI (σ/μ × 100), %</li>
            <li><strong>CR σ</strong> - стандартное отклонение конверсии в лиды, %</li>
            <li><strong>CR CV</strong> - коэффициент вариации конверсии, %</li>
            <li><strong>Approve Rate σ</strong> - стандартное отклонение процента апрувов (для CPA кампаний), %</li>
            <li><strong>Approve Rate CV</strong> - коэффициент вариации апрувов, %</li>
            <li><strong>Средний ROI</strong> - средняя рентабельность за период, %</li>
            <li><strong>Средний CR</strong> - средняя конверсия за период, %</li>
            <li><strong>Средний Approve Rate</strong> - средний процент апрувов за период, %</li>
            <li><strong>Дней с данными</strong> - количество дней с активностью в анализируемом периоде</li>
            <li><strong>Классификация</strong> - low (низкая <20%), medium (средняя 20-50%), high (высокая >50%)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_spend: 'Минимальный расход в день',
            min_days_with_data: 'Минимум дней с данными'
        },

        /**
         * Отрисовка таблицы для volatility_calculator
         */
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
                                    ${renderSortableHeader('overall_volatility', 'Волатильность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('volatility_class', 'Класс', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_cv', 'ROI CV', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr_cv', 'CR CV', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'Средний ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_cr', 'Средний CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_with_data', 'Дней', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Волатильность с цветом
                    let volatilityClass = 'text-success';
                    if (campaign.overall_volatility >= 50) volatilityClass = 'text-danger';
                    else if (campaign.overall_volatility >= 20) volatilityClass = 'text-warning';

                    // Класс badge
                    const classBadges = {
                        'low': '<span class="badge bg-success">Низкая</span>',
                        'medium': '<span class="badge bg-warning">Средняя</span>',
                        'high': '<span class="badge bg-danger">Высокая</span>',
                        'extreme': '<span class="badge bg-dark">Экстремальная</span>'
                    };
                    const classBadge = classBadges[campaign.volatility_class] || campaign.volatility_class;

                    // ROI цвет
                    const roiClass = campaign.avg_roi >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${volatilityClass}">${campaign.overall_volatility.toFixed(1)}%</strong></td>
                            <td>${classBadge}</td>
                            <td>${campaign.roi_cv.toFixed(1)}%</td>
                            <td>${campaign.cr_cv.toFixed(1)}%</td>
                            <td class="${roiClass}">${campaign.avg_roi.toFixed(2)}%</td>
                            <td>${campaign.avg_cr.toFixed(2)}%</td>
                            <td>${campaign.days_with_data}</td>
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
        ModuleRegistry.register(VolatilityCalculatorModule);
    }
})();
