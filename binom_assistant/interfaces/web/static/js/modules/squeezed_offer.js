/**
 * Модуль: Отжатый оффер
 * Обнаруживает офферы с падением CR или процента апрувов
 */
(function() {
    const SqueezedOfferModule = {
        id: 'squeezed_offer',

        translations: {
            total_found: 'Всего найдено',
            critical_count: 'Критических',
            high_count: 'Высокой важности',
            medium_count: 'Средней важности',
            avg_cr_drop: 'Среднее падение CR',
            avg_approve_rate_drop: 'Среднее падение апрувов'
        },

        algorithm: `
            <ol>
                <li>Сравниваются два периода: текущие 7 дней включительно vs предыдущие 7 дней</li>
                <li>Проверяется стабильность трафика (изменение объема кликов ±20%)</li>
                <li>Фильтруются кампании с минимум 20 лидами за текущий период</li>
                <li>Вычисляется CR (Conversion Rate) для обоих периодов</li>
                <li>Вычисляется Approve Rate (процент апрувов от всех лидов включая hold и rejected)</li>
                <li>Обнаруживаются кампании с падением CR > 40% ИЛИ падением Approve Rate > 40%</li>
                <li>Определяется критичность: critical (>60%), high (>50%), medium (>40%)</li>
                <li>Формируются рекомендации по проверке лендингов и требований партнёрок</li>
            </ol>
        `,

        metrics: `
            <li><strong>CR (Conversion Rate)</strong> - конверсия из кликов в лиды, %</li>
            <li><strong>Approve Rate</strong> - процент апрувленных лидов от всех лидов (включая hold и rejected), %</li>
            <li><strong>CR Change</strong> - изменение конверсии между периодами, %</li>
            <li><strong>Approve Rate Change</strong> - изменение процента апрувов между периодами, %</li>
            <li><strong>ROI</strong> - возврат инвестиций, %</li>
            <li><strong>Problem Type</strong> - тип проблемы (падение CR, падение апрувов или оба)</li>
            <li><strong>Traffic Stability</strong> - стабильность объема трафика между периодами</li>
            <li><strong>Текущий период</strong> - последние 7 дней включая сегодня</li>
            <li><strong>Предыдущий период</strong> - 7 дней до текущего периода</li>
            <li><strong>Минимум лидов</strong> - 20 лидов за текущий период для включения в анализ</li>
            <li><strong>Порог падения CR</strong> - 40% (настраивается)</li>
            <li><strong>Порог падения апрувов</strong> - 40% (настраивается)</li>
            <li><strong>Стабильность трафика</strong> - ±20% изменения кликов (настраивается)</li>
        `,

        paramTranslations: {
            days: 'Период анализа',
            cr_drop_threshold: 'Порог падения CR',
            approve_drop_threshold: 'Порог падения апрувов',
            min_leads: 'Минимум лидов',
            traffic_stability: 'Стабильность трафика'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.offers) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const offers = results.data.offers;
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    ${renderSortableHeader('offer_name', 'Оффер', 'text', sortState.column, sortState.direction)}
                                    <th>Гео</th>
                                    ${renderSortableHeader('problem_type', 'Тип проблемы', 'text', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_cr', 'Текущий CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_cr', 'Предыдущий CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cr_change', 'Изм. CR', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_approve_rate', 'Текущий Approve', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('previous_approve_rate', 'Предыдущий Approve', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('approve_rate_change', 'Изм. Approve', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_roi', 'Текущий ROI', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('current_leads', 'Лиды', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('severity', 'Статус', 'severity', sortState.column, sortState.direction)}
                                </tr>
                            </thead>
                            <tbody>
                `;

                offers.forEach(offer => {
                    const offerId = offer.offer_id || 'N/A';
                    const geoText = offer.geo || '-';

                    html += `
                        <tr>
                            <td>
                                <strong>[${offerId}] ${this._escapeHtml(offer.offer_name || 'Unknown')}</strong>
                            </td>
                            <td>${geoText}</td>
                            <td><span class="badge badge-warning">${offer.problem_type}</span></td>
                            <td>${offer.current_cr.toFixed(2)}%</td>
                            <td>${offer.previous_cr.toFixed(2)}%</td>
                            <td class="${offer.cr_change < 0 ? 'text-danger' : 'text-success'}">${offer.cr_change > 0 ? '+' : ''}${offer.cr_change.toFixed(1)}%</td>
                            <td>${offer.current_approve_rate.toFixed(2)}%</td>
                            <td>${offer.previous_approve_rate.toFixed(2)}%</td>
                            <td class="${offer.approve_rate_change < 0 ? 'text-danger' : 'text-success'}">${offer.approve_rate_change > 0 ? '+' : ''}${offer.approve_rate_change.toFixed(1)}%</td>
                            <td>${formatROI(offer.current_roi)}</td>
                            <td>${offer.current_leads}</td>
                            <td>${formatSeverity(offer.severity)}</td>
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

        _escapeHtml: function(text) {
            if (!text) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return text.replace(/[&<>"']/g, m => map[m]);
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(SqueezedOfferModule);
    }
})();
