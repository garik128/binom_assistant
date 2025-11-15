/**
 * Модуль: Рейтинг офферов (Offer Profitability Ranker)
 * Ранжирует офферы по комплексной прибыльности
 */
(function() {
    const OfferProfitabilityRankerModule = {
        id: 'offer_profitability_ranker',

        translations: {
            rank: 'Ранг',
            offer_name: 'Оффер',
            avg_roi: 'ROI (%)',
            total_profit: 'Прибыль',
            stability_score: 'Стабильность',
            scaling_potential: 'Потенциал',
            final_score: 'Финальный балл',
            total_cost: 'Расход',
            total_revenue: 'Доход',
            is_cpa: 'Тип',
            total_offers: 'Всего офферов',
            avg_roi_portfolio: 'Средний ROI портфеля',
            profitable_offers: 'Прибыльных офферов',
            declining_offers: 'Убыточных офферов',
            total_profit_portfolio: 'Общая прибыль портфеля',
            cpa_offers: 'CPA офферов',
            cpl_offers: 'CPL офферов'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Группировка кампаний по офферам (группам)</li>
                <li>Фильтрация офферов с расходом < min_cost</li>
                <li>Расчет компонентов рейтинга:
                    <ol>
                        <li><strong>Средний ROI (40%)</strong>:
                            <ul>
                                <li>ROI = ((revenue - cost) / cost) * 100</li>
                                <li>score = max(0, min(100, 50 + ROI/2))</li>
                            </ul>
                        </li>
                        <li><strong>Объем прибыли (30%)</strong>:
                            <ul>
                                <li>profit = revenue - cost</li>
                                <li>score = min(100, 50 + volume_score + roi_bonus)</li>
                            </ul>
                        </li>
                        <li><strong>Стабильность апрувов (20%)</strong>:
                            <ul>
                                <li>Для CPA: approval_rate = approved_leads / total_leads * 100</li>
                                <li>score = стабильность между 20-80%</li>
                                <li>Для CPL: базовое значение 75</li>
                            </ul>
                        </li>
                        <li><strong>Потенциал масштабирования (10%)</strong>:
                            <ul>
                                <li>Количество кампаний (больше = стабильнее)</li>
                                <li>Консистентность ROI (низкая волатильность)</li>
                                <li>Наличие margin > 30%</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет финального рейтинга:
                    <ul>
                        <li>final_score = roi_score*0.40 + profit_score*0.30 + stability*0.20 + scaling*0.10</li>
                    </ul>
                </li>
                <li>Сортировка по финальному рейтингу (по убыванию)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Final Score</strong> - комплексный рейтинг офера (0-100)</li>
            <li><strong>Average ROI</strong> - средний ROI по офферу (%)</li>
            <li><strong>Total Profit</strong> - абсолютная прибыль по офферу ($)</li>
            <li><strong>Stability Score</strong> - стабильность апрувов для CPA (0-100)</li>
            <li><strong>Scaling Potential</strong> - потенциал масштабирования (0-100)</li>
            <li><strong>Rank</strong> - позиция в рейтинге</li>
            <li><strong>Total Cost</strong> - общий расход по офферу ($)</li>
            <li><strong>Total Revenue</strong> - общий доход по офферу ($)</li>
            <li><strong>Type</strong> - тип офера (CPA или CPL)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cost: 'Минимальный расход ($)',
            min_roi_for_scaling: 'Минимальный ROI для масштабирования (%)',
            min_approval_rate: 'Мин. норма апрува (%)',
            max_approval_rate: 'Макс. норма апрува (%)'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.offers) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const offers = data.offers || [];
            const period = data.period || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    ${renderSortableHeader('rank', 'Ранг', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('offer_name', 'Оффер', 'text', sortState.column, sortState.direction)}
                                    <th>Гео</th>
                                    ${renderSortableHeader('avg_roi', 'ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_profit', 'Прибыль', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Расход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Доход', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('stability_score', 'Стабильность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('scaling_potential', 'Потенциал', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('final_score', 'Финальный балл', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('is_cpa', 'Тип', 'text', sortState.column, sortState.direction)}
                                </tr>
                            </thead>
                            <tbody>
                `;

                offers.forEach((offer) => {
                    const offerType = offer.is_cpa ? 'CPA' : 'CPL';
                    const offerId = offer.offer_id || 'N/A';
                    const geoText = offer.geo || '-';

                    html += `
                        <tr>
                            <td><strong>#${offer.rank}</strong></td>
                            <td><strong>[${offerId}] ${this._escapeHtml(offer.offer_name || 'Unknown')}</strong></td>
                            <td>${geoText}</td>
                            <td>${formatROI(offer.avg_roi)}</td>
                            <td>${formatProfit(offer.total_profit)}</td>
                            <td>${formatCurrency(offer.total_cost)}</td>
                            <td>${formatCurrency(offer.total_revenue)}</td>
                            <td>${offer.stability_score.toFixed(1)}</td>
                            <td>${offer.scaling_potential.toFixed(1)}</td>
                            <td><strong>${offer.final_score.toFixed(1)}</strong></td>
                            <td>${offerType}</td>
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
                        <strong>Период:</strong> ${period.days || 7} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
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
        ModuleRegistry.register(OfferProfitabilityRankerModule);
    }
})();
