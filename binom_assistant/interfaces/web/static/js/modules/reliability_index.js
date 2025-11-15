/**
 * Модуль: Надёжность (Reliability Index)
 * Комплексная оценка надежности для масштабирования
 */
(function() {
    const ReliabilityIndexModule = {
        id: 'reliability_index',

        translations: {
            total_analyzed: 'Проанализировано кампаний',
            total_high: 'Высокая надежность',
            total_medium: 'Средняя надежность',
            total_low: 'Низкая надежность',
            avg_reliability_index: 'Средний индекс надежности',
            best_reliability_index: 'Лучший индекс',
            worst_reliability_index: 'Худший индекс',
            avg_campaign_age: 'Средний возраст кампаний (дней)'
        },

        algorithm: `
            <ol>
                <li>Загружается дневная статистика кампаний за указанный период (по умолчанию 30 дней)</li>
                <li>Для каждой кампании определяется возраст (дни с первого запуска)</li>
                <li>Рассчитывается стабильность ROI через коэффициент вариации (std_dev/mean)</li>
                <li>Оценивается объем данных: количество кликов и лидов за период</li>
                <li>Вычисляется индекс консистентности: процент прибыльных дней, соотношение прибыль/убыток, максимальная просадка</li>
                <li>Финальный индекс надежности (0-100) складывается из компонентов с весами: возраст 20%, стабильность ROI 30%, объем данных 25%, консистентность 25%</li>
                <li>Возраст кампании: макс балл при 60+ днях работы</li>
                <li>Стабильность ROI: чем ниже вариация, тем выше балл (CV < 20% = макс балл)</li>
                <li>Объем данных: учитываются клики (макс при 1000+) и лиды (макс при min_leads+)</li>
                <li>Консистентность: комбинация прибыльных дней, соотношения и просадки</li>
                <li>Классификация: высокая (≥70 по умолчанию), средняя (50-70), низкая (<50)</li>
                <li>Фильтруются кампании с минимальным расходом ($1/день) и количеством дней с данными (14 дней)</li>
                <li>Формируются алерты для высоконадежных кампаний (готовы к масштабированию), низконадежных (предупреждения) и молодых перспективных кампаний</li>
            </ol>
        `,

        metrics: `
            <li><strong>Индекс надежности</strong> - комплексная оценка надежности кампании (0-100), чем выше, тем надежнее</li>
            <li><strong>Возраст кампании (дней)</strong> - количество дней с момента первого запуска кампании</li>
            <li><strong>Балл возраста</strong> - оценка возраста кампании (0-100), максимум при 60+ днях</li>
            <li><strong>Балл стабильности</strong> - оценка стабильности ROI (0-100), чем ниже вариация, тем выше балл</li>
            <li><strong>Балл объема</strong> - оценка объема данных (0-100), учитываются клики и лиды</li>
            <li><strong>Балл консистентности</strong> - оценка консистентности прибыли (0-100)</li>
            <li><strong>CV ROI</strong> - коэффициент вариации ROI (%), чем меньше, тем стабильнее</li>
            <li><strong>Общее количество кликов</strong> - суммарное количество кликов за период</li>
            <li><strong>Общее количество лидов</strong> - суммарное количество лидов за период</li>
            <li><strong>Процент прибыльных дней</strong> - доля прибыльных дней от общего количества, %</li>
            <li><strong>Общая прибыль</strong> - суммарная прибыль за период (revenue - cost), $</li>
            <li><strong>Средний ROI</strong> - средняя рентабельность за период, %</li>
            <li><strong>Дней с данными</strong> - количество дней с активностью в анализируемом периоде</li>
            <li><strong>Классификация</strong> - high (высокая), medium (средняя), low (низкая)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_spend: 'Минимальный расход в день',
            min_days_with_data: 'Минимум дней с данными',
            reliability_threshold: 'Порог высокой надежности',
            min_leads: 'Минимум лидов'
        },

        /**
         * Отрисовка таблицы для reliability_index
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
                                    ${renderSortableHeader('reliability_index', 'Индекс', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('reliability_class', 'Класс', 'string', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('campaign_age_days', 'Возраст', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('age_score', 'Балл возраста', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('stability_score', 'Балл стаб.', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('volume_score', 'Балл объема', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('consistency_score', 'Балл конс.', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_roi', 'Средний ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Индекс надежности с цветом
                    let scoreClass = 'text-success';
                    if (campaign.reliability_index < 50) scoreClass = 'text-danger';
                    else if (campaign.reliability_index < 70) scoreClass = 'text-warning';

                    // Класс badge
                    const classBadges = {
                        'high': '<span class="badge bg-success">Высокая</span>',
                        'medium': '<span class="badge bg-warning">Средняя</span>',
                        'low': '<span class="badge bg-danger">Низкая</span>'
                    };
                    const classBadge = classBadges[campaign.reliability_class] || campaign.reliability_class;

                    // ROI цвет
                    const roiClass = campaign.avg_roi >= 0 ? 'text-success' : 'text-danger';

                    // Прибыль цвет
                    const profitClass = campaign.total_profit >= 0 ? 'text-success' : 'text-danger';

                    html += `
                        <tr>
                            <td><strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br><small class="text-muted">${escapeHtml(campaign.group)}</small></td>
                            <td><strong class="${scoreClass}">${campaign.reliability_index.toFixed(1)}</strong></td>
                            <td>${classBadge}</td>
                            <td>${campaign.campaign_age_days} дн.</td>
                            <td>${campaign.age_score.toFixed(1)}</td>
                            <td>${campaign.stability_score.toFixed(1)}</td>
                            <td>${campaign.volume_score.toFixed(1)}</td>
                            <td>${campaign.consistency_score.toFixed(1)}</td>
                            <td class="${roiClass}">${campaign.avg_roi.toFixed(2)}%</td>
                            <td class="${profitClass}">${formatCurrency(campaign.total_profit)}</td>
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
        ModuleRegistry.register(ReliabilityIndexModule);
    }
})();
