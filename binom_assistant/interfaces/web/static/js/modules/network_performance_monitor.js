/**
 * Модуль: Эффективность сетей (Network Performance Monitor)
 * Мониторит эффективность партнерских сетей и их метрики
 */
(function() {
    const NetworkPerformanceMonitorModule = {
        id: 'network_performance_monitor',

        translations: {
            networks: 'Сети',
            avg_approve_rate: 'Средний Approve Rate (%)',
            avg_approval_delay: 'Средняя задержка апрувов (дней)',
            active_offers: 'Активные офферы',
            total_roi: 'Общий ROI (%)',
            performance_score: 'Performance Score',
            status: 'Статус',
            total_cost: 'Общий расход ($)',
            total_revenue: 'Общий доход ($)',
            total_networks: 'Всего сетей',
            avg_performance_score: 'Средний Performance Score',
            best_network: 'Лучшая сеть',
            worst_network: 'Худшая сеть',
            high_performers: 'Высокоэффективных',
            low_performers: 'Низкоэффективных'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по партнерским сетям за период</li>
                <li>Фильтрация шума (расход < 1$ или клики < 50)</li>
                <li>Анализ по сетям:
                    <ol>
                        <li><strong>Средний Approve Rate</strong>:
                            <ul>
                                <li>approve_rate = (total_approved_leads / total_leads) * 100</li>
                            </ul>
                        </li>
                        <li><strong>Средняя задержка апрувов</strong>:
                            <ul>
                                <li>Анализ дневных данных: время между появлением лидов и их апрувом</li>
                                <li>avg_approval_delay = средняя задержка в днях</li>
                            </ul>
                        </li>
                        <li><strong>Количество активных офферов</strong>:
                            <ul>
                                <li>Подсчет офферов в сети с данными за период</li>
                            </ul>
                        </li>
                        <li><strong>Общий ROI</strong>:
                            <ul>
                                <li>ROI = ((total_revenue - total_cost) / total_cost) * 100</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет Performance Score (0-100):
                    <ol>
                        <li>Approve Rate Score (40% вес): approve_rate * 1.0 (макс 100)</li>
                        <li>Approval Delay Score (25% вес): 100 - (delay_days / 7 * 100)</li>
                        <li>ROI Score (25% вес): 50 + (ROI / 2)</li>
                        <li>Volume Score (10% вес): бонус за количество офферов</li>
                        <li>total_score = sum(weighted_components)</li>
                    </ol>
                </li>
                <li>Определение статуса:
                    <ul>
                        <li><strong>Excellent</strong>: score >= 80 AND approve_rate >= 50 AND ROI > 0</li>
                        <li><strong>Good</strong>: score >= 60 AND approve_rate >= 30</li>
                        <li><strong>Average</strong>: score >= 40</li>
                        <li><strong>Poor</strong>: score < 40</li>
                    </ul>
                </li>
            </ol>
        `,

        metrics: `
            <li><strong>Average Approve Rate</strong> - средний процент одобренных лидов по сети (%)</li>
            <li><strong>Average Approval Delay</strong> - средняя задержка между появлением лида и его апрувом (дней)</li>
            <li><strong>Active Offers</strong> - количество активных офферов в сети</li>
            <li><strong>Total ROI</strong> - общая рентабельность инвестиций по сети (%)</li>
            <li><strong>Performance Score</strong> - комплексный скор эффективности сети (0-100)</li>
            <li><strong>Status</strong> - статус сети (excellent/good/average/poor)</li>
            <li><strong>Total Cost</strong> - общий расход по сети ($)</li>
            <li><strong>Total Revenue</strong> - общий доход по сети ($)</li>
            <li><strong>Average Performance Score</strong> - средний скор по всем сетям</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cost: 'Минимальный расход ($)',
            slow_approval_threshold: 'Порог медленного апрува (дней)',
            many_campaigns_threshold: 'Порог многих офферов'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.networks) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const networks = data.networks || [];
            const summary = data.summary || {};
            const period = data.period || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';

                // Таблица сетей (summary отрисовывается отдельно в resultsSummary)
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    ${renderSortableHeader('network', 'Группа', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('active_offers', 'Офферов', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_roi', 'ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_approve_rate', 'Approve Rate (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_approval_delay', 'Задержка (ч)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('performance_score', 'Индекс', 'number', sortState.column, sortState.direction)}
                                    <th>Статус</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                networks.forEach(network => {
                    const statusText = this._getStatusText(network.status);

                    html += `
                        <tr>
                            <td><strong>${this._escapeHtml(network.network)}</strong></td>
                            <td>${network.active_offers}</td>
                            <td>${formatCurrency(network.total_cost)}</td>
                            <td>${formatCurrency(network.total_revenue)}</td>
                            <td>${formatROI(network.total_roi)}</td>
                            <td>${network.avg_approve_rate.toFixed(1)}%</td>
                            <td>${network.avg_approval_delay.toFixed(1)}</td>
                            <td>${network.performance_score.toFixed(1)}</td>
                            <td><span class="status-badge status-${network.status}">${statusText}</span></td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;

                // Info banner
                html += `
                    <div class="info-banner">
                        <strong>Период:</strong> ${period.days || 14} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, networks, (col, dir) => render(), sortState);
            };

            render();
        },

        _getStatusText: function(status) {
            const texts = {
                'excellent': 'Отличная',
                'good': 'Хорошая',
                'average': 'Средняя',
                'poor': 'Плохая'
            };
            return texts[status] || status;
        },

        _escapeHtml: function(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(NetworkPerformanceMonitorModule);
    }
})();
