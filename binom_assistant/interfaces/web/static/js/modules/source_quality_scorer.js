/**
 * Модуль: Качество источников
 * Оценивает качество источников трафика по CR, approve rate, стабильности и CPC
 */
(function() {
    const SourceQualityScorerModule = {
        id: 'source_quality_scorer',

        translations: {
            excellent: 'Отличное',
            good: 'Хорошее',
            medium: 'Среднее',
            poor: 'Плохое',
            total_sources: 'Всего источников',
            avg_quality_score: 'Средний индекс качества',
            excellent_sources: 'Отличных источников',
            poor_sources: 'Плохих источников',
            excellent_count: 'Отличных',
            good_count: 'Хороших',
            medium_count: 'Средних',
            poor_count: 'Плохих',
            avg_quality: 'Средний индекс'
        },

        algorithm: `
            <ol>
                <li>Анализируется статистика источников за указанный период (по умолчанию 7 дней)</li>
                <li>Фильтруются источники с количеством кликов менее 100 (настраивается)</li>
                <li>Рассчитывается средний CR для каждого источника</li>
                <li>Рассчитывается approve rate для каждого источника (для CPA кампаний)</li>
                <li>Оценивается стабильность поставки трафика (процент дней с активностью)</li>
                <li>Вычисляется средний CPC для каждого источника</li>
                <li>Формируется общий качественный индекс (0-100) на основе взвешивания 4 метрик</li>
                <li>Присваивается рейтинг: excellent (80+), good (60-79), medium (40-59), poor (<40)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Average CR (Conversion Rate)</strong> - средний процент конверсии по источнику, %</li>
            <li><strong>Approve Rate</strong> - процент одобренных лидов, %</li>
            <li><strong>Stability Score</strong> - стабильность поставки трафика, %</li>
            <li><strong>Average CPC (Cost Per Click)</strong> - средняя стоимость за клик, $</li>
            <li><strong>Quality Score</strong> - комбинированный индекс качества (0-100)</li>
            <li><strong>Рейтинг</strong> - категория качества источника</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_clicks: 'Минимум кликов',
            excellent_threshold: 'Порог отличного качества',
            good_threshold: 'Порог хорошего качества',
            poor_threshold: 'Порог низкого качества',
            unstable_threshold: 'Порог нестабильности'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.sources) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const sources = results.data.sources;
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Источник</th>
                                    ${renderSortableHeader('avg_cr', 'CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('approve_rate', 'Approve Rate', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('stability_score', 'Стабильность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_cpc', 'CPC', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('quality_score', 'Качество', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('rating', 'Рейтинг', 'text', sortState.column, sortState.direction)}
                                    <th>Клики</th>
                                    <th>Лиды</th>
                                    <th>Кампании</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                sources.forEach(source => {
                    const ratingClass =
                        source.rating === 'excellent' ? 'excellent' :
                        source.rating === 'good' ? 'good' :
                        source.rating === 'medium' ? 'medium' :
                        'poor';

                    const ratingText =
                        source.rating === 'excellent' ? 'Отличное' :
                        source.rating === 'good' ? 'Хорошее' :
                        source.rating === 'medium' ? 'Среднее' :
                        'Плохое';

                    html += `
                        <tr>
                            <td><strong>${escapeHtml(source.source)}</strong></td>
                            <td>${source.avg_cr.toFixed(2)}%</td>
                            <td>${source.approve_rate.toFixed(1)}%</td>
                            <td>${source.stability_score.toFixed(1)}%</td>
                            <td>$${source.avg_cpc.toFixed(4)}</td>
                            <td>
                                <div class="quality-bar">
                                    <div class="quality-fill" style="width: ${Math.min(source.quality_score, 100)}%;
                                        background-color: ${
                                            source.quality_score >= 80 ? '#28a745' :
                                            source.quality_score >= 60 ? '#17a2b8' :
                                            source.quality_score >= 40 ? '#ffc107' :
                                            '#dc3545'
                                        }"></div>
                                    <span class="quality-text">${source.quality_score.toFixed(1)}</span>
                                </div>
                            </td>
                            <td><span class="badge badge-${ratingClass}">${ratingText}</span></td>
                            <td>${source.total_clicks}</td>
                            <td>${source.total_leads}</td>
                            <td>${source.campaigns_count}</td>
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
                attachTableSortHandlers(container, sources, (col, dir) => render(), sortState);
            };

            render();
        },

        render: function(results, container) {
            // Создаем две секции: сводка и таблица
            const summaryContainer = document.createElement('div');
            const tableContainer = document.createElement('div');

            container.innerHTML = '';
            container.appendChild(summaryContainer);
            container.appendChild(tableContainer);

            // Рендерим сводку
            this.renderSummary(results, summaryContainer);

            // Рендерим таблицу
            const tableSection = document.createElement('div');
            tableSection.className = 'section-card';
            const tableTitle = document.createElement('h3');
            tableTitle.textContent = 'Источники';
            tableSection.appendChild(tableTitle);
            tableSection.appendChild(tableContainer);
            container.appendChild(tableSection);

            this.renderTable(results, tableContainer);
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SourceQualityScorerModule);
    }
})();
