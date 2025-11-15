/**
 * Модуль: Заснувшие кампании
 * Находит остановившиеся кампании
 */
(function() {
    const SleepyCampaignFinderModule = {
        id: 'sleepy_campaign_finder',

        translations: {
            total_sleepy: 'Заснувших кампаний',
            critical_count: 'Критично (полная остановка)',
            high_count: 'Высокий (падение >95%)',
            medium_count: 'Средний (падение >90%)',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по кликам за последние (recent_days + history_days) дней</li>
                <li>Разделение данных на два периода:
                    <ul>
                        <li><strong>History</strong>: дни с -${7+3} по -${3} (предыдущие 7 дней)</li>
                        <li><strong>Recent</strong>: дни с -${3} по сегодня (последние 3 дня)</li>
                    </ul>
                </li>
                <li>Подсчет кликов в каждом периоде (clicks_before, clicks_recent)</li>
                <li>Фильтрация: только кампании с clicks_before >= min_clicks_before</li>
                <li>Расчет падения: drop_percent = (clicks_before - clicks_recent) / clicks_before * 100</li>
                <li>Критерии "заснувшей":
                    <ul>
                        <li>clicks_recent == 0 (полная остановка) → severity: critical</li>
                        <li>ИЛИ drop_percent >= drop_threshold → severity: high/medium</li>
                    </ul>
                </li>
                <li>Определение последней активности и дней молчания</li>
                <li>Сортировка по clicks_before DESC (самые активные сначала)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Кликов/день до</strong> - среднее количество кликов в день в период "история"</li>
            <li><strong>Кликов/день сейчас</strong> - среднее количество кликов в день в период "сейчас"</li>
            <li><strong>Падение (%)</strong> - процент падения среднедневного трафика (сравнение avg_before vs avg_recent)</li>
            <li><strong>Всего до/сейчас</strong> - общее количество кликов за весь период (дополнительная информация)</li>
            <li><strong>Последняя активность</strong> - дата последней активности (клики > 0)</li>
            <li><strong>Дней молчания</strong> - количество дней с момента последней активности</li>
            <li><strong>Критичность</strong> - уровень важности (критично/высокий/средний)</li>
        `,

        paramTranslations: {
            recent_days: 'Дней тишины',
            history_days: 'Дней истории',
            min_clicks_before: 'Минимум кликов до',
            drop_threshold: 'Порог падения (%)'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.sleepy_campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const sleepyCampaigns = results.data.sleepy_campaigns;
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
                                    ${renderSortableHeader('avg_clicks_before', 'Кликов/день до', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_clicks_recent', 'Кликов/день сейчас', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('drop_percent', 'Падение (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('clicks_before', 'Всего до', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('clicks_recent', 'Всего сейчас', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('last_activity_date', 'Последняя активность', 'date', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('days_silent', 'Дней молчания', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity_label', 'Критичность', 'text', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                sleepyCampaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет severity badge
                    let severityClass = 'badge-secondary';
                    if (campaign.severity === 'critical') {
                        severityClass = 'badge-danger';
                    } else if (campaign.severity === 'high') {
                        severityClass = 'badge-warning';
                    } else if (campaign.severity === 'medium') {
                        severityClass = 'badge-info';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td><strong>${formatNumber(campaign.avg_clicks_before)}</strong></td>
                            <td><strong>${formatNumber(campaign.avg_clicks_recent)}</strong></td>
                            <td>
                                <span class="text-danger">
                                    <strong>${campaign.drop_percent}%</strong>
                                </span>
                            </td>
                            <td><small class="text-muted">${formatNumber(campaign.clicks_before)}</small></td>
                            <td><small class="text-muted">${formatNumber(campaign.clicks_recent)}</small></td>
                            <td>${campaign.last_activity_date ? formatDate(campaign.last_activity_date) : 'N/A'}</td>
                            <td>
                                <strong>${campaign.days_silent}</strong> дней
                            </td>
                            <td>
                                <span class="badge ${severityClass}">
                                    ${campaign.severity_label}
                                </span>
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
                        <strong>Период проверки:</strong>
                        History: ${period.history_days || 7} дней |
                        Recent: ${period.recent_days || 3} дней |
                        <strong>Дата разделения:</strong> ${formatDate(period.split_date)}
                    </div>
                `;

                container.innerHTML = html;

                // Подключаем сортировку
                attachTableSortHandlers(container, sleepyCampaigns, (col, dir) => render(), sortState);
            };

            render();
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SleepyCampaignFinderModule);
    }
})();
