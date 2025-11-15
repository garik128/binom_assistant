/**
 * Модуль: Готовы к росту (Scaling Candidates)
 * Выявляет стабильные прибыльные кампании, готовые к масштабированию
 */
(function() {
    const ScalingCandidatesModule = {
        id: 'scaling_candidates',

        translations: {
            total_candidates: 'Кандидатов для масштабирования',
            avg_roi: 'Средний ROI (%)',
            avg_readiness_score: 'Средняя готовность',
            total_checked: 'Проверено кампаний'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по кампаниям за период (по умолчанию 14 дней)</li>
                <li>Расчет средних дневных метрик:
                    <ul>
                        <li>avg_daily_spend = total_cost / days_with_data</li>
                    </ul>
                </li>
                <li>Фильтрация: avg_daily_spend >= min_daily_spend</li>
                <li>Расчет дневных ROI для анализа волатильности:
                    <ul>
                        <li>ROI = ((revenue - cost) / cost) * 100</li>
                    </ul>
                </li>
                <li>Расчет статистики ROI:
                    <ul>
                        <li>avg_roi = mean(daily_roi_values)</li>
                        <li>min_roi = min(daily_roi_values)</li>
                    </ul>
                </li>
                <li>Фильтрация: avg_roi >= roi_threshold AND min_roi >= roi_threshold</li>
                <li>Расчет волатильности (коэффициент вариации):
                    <ul>
                        <li>CV = std_dev(daily_roi) / mean(daily_roi)</li>
                    </ul>
                </li>
                <li>Фильтрация: roi_volatility <= volatility_threshold</li>
                <li>Разделение периода на две половины для анализа CPC:
                    <ul>
                        <li>cpc_first_half = first_half_cost / first_half_clicks</li>
                        <li>cpc_second_half = second_half_cost / second_half_clicks</li>
                        <li>cpc_growth_percent = ((cpc_second_half - cpc_first_half) / cpc_first_half) * 100</li>
                    </ul>
                </li>
                <li>Фильтрация: cpc_growth_percent <= cpc_growth_limit</li>
                <li>Расчет готовности к масштабированию (readiness_score):
                    <ul>
                        <li>readiness_score = 100 - (roi_volatility * 100) - (cpc_growth * 0.5) - max(0, (50 - min_roi))</li>
                        <li>Ограничение: 0 <= readiness_score <= 100</li>
                    </ul>
                </li>
                <li>Сортировка: по readiness_score DESC</li>
            </ol>
        `,

        metrics: `
            <li><strong>Avg ROI</strong> - средний ROI за период (%)</li>
            <li><strong>Min ROI</strong> - минимальный ROI за период (%)</li>
            <li><strong>ROI Volatility</strong> - коэффициент вариации ROI (CV)</li>
            <li><strong>Avg Daily Spend</strong> - средний расход в день ($)</li>
            <li><strong>CPC Growth</strong> - рост CPC между первой и второй половиной периода (%)</li>
            <li><strong>Readiness Score</strong> - комплексная оценка готовности к масштабированию (0-100)</li>
            <li><strong>Total Cost</strong> - общий расход за период ($)</li>
            <li><strong>Total Revenue</strong> - общий доход за период ($)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            roi_threshold: 'Минимальный ROI (%)',
            min_daily_spend: 'Минимальный расход в день ($)',
            volatility_threshold: 'Порог волатильности',
            cpc_growth_limit: 'Максимальный рост CPC (%)'
        },

        renderTable: function(results, container) {
            if (!results.data || !results.data.campaigns) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const campaigns = results.data.campaigns;
            const period = results.data.period || {};
            const params = results.data.params || {};
            const sortState = {column: null, direction: 'asc'};

            const render = () => {
                let html = '';
                html += `
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Кампания</th>
                                    ${renderSortableHeader('avg_roi', 'Средний ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('min_roi', 'Мин. ROI (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('roi_volatility', 'Волатильность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('avg_daily_spend', 'Расход в день ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('cpc_growth_percent', 'Рост CPC (%)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('readiness_score', 'Готовность', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_cost', 'Всего расход ($)', 'number', sortState.column, sortState.direction)}
                                    ${renderSortableHeader('total_revenue', 'Всего доход ($)', 'number', sortState.column, sortState.direction)}
                                    <th>Binom</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                campaigns.forEach(campaign => {
                    const binomId = campaign.binom_id || campaign.campaign_id;

                    // Определяем цвет для readiness_score
                    let readinessClass = 'badge-danger';
                    let readinessLabel = 'Низкая';
                    if (campaign.readiness_score >= 90) {
                        readinessClass = 'badge-success';
                        readinessLabel = 'Высокая';
                    } else if (campaign.readiness_score >= 80) {
                        readinessClass = 'badge-info';
                        readinessLabel = 'Хорошая';
                    } else if (campaign.readiness_score >= 70) {
                        readinessClass = 'badge-warning';
                        readinessLabel = 'Средняя';
                    }

                    // Цвет для ROI
                    let roiClass = 'text-success';
                    if (campaign.avg_roi < 70) {
                        roiClass = 'text-info';
                    }

                    // Цвет для волатильности
                    let volatilityClass = 'text-success';
                    if (campaign.roi_volatility > 0.2) {
                        volatilityClass = 'text-warning';
                    }

                    // Цвет для роста CPC
                    let cpcGrowthClass = 'text-success';
                    if (campaign.cpc_growth_percent > 15) {
                        cpcGrowthClass = 'text-warning';
                    } else if (campaign.cpc_growth_percent > 10) {
                        cpcGrowthClass = 'text-info';
                    }

                    html += `
                        <tr>
                            <td>
                                <strong>[${binomId}] ${escapeHtml(campaign.name)}</strong><br>
                                <small class="text-muted">${escapeHtml(campaign.group)}</small>
                            </td>
                            <td>
                                <span class="${roiClass}">
                                    <strong>${campaign.avg_roi.toFixed(1)}%</strong>
                                </span>
                            </td>
                            <td>
                                ${campaign.min_roi.toFixed(1)}%
                            </td>
                            <td>
                                <span class="${volatilityClass}">
                                    ${campaign.roi_volatility.toFixed(2)}
                                </span>
                                <br><small class="text-muted">${campaign.roi_volatility < 0.2 ? 'низкая' : campaign.roi_volatility < 0.3 ? 'средняя' : 'высокая'}</small>
                            </td>
                            <td>
                                <strong>$${campaign.avg_daily_spend.toFixed(2)}</strong>
                            </td>
                            <td>
                                <span class="${cpcGrowthClass}">
                                    ${campaign.cpc_growth_percent.toFixed(1)}%
                                </span>
                                <br><small class="text-muted">
                                    $${campaign.cpc_first_half.toFixed(4)} &rarr; $${campaign.cpc_second_half.toFixed(4)}
                                </small>
                            </td>
                            <td>
                                <span class="badge ${readinessClass}">
                                    ${campaign.readiness_score.toFixed(1)}
                                </span>
                                <br><small class="text-muted">${readinessLabel}</small>
                            </td>
                            <td>
                                $${campaign.total_cost.toFixed(2)}
                            </td>
                            <td>
                                <span class="text-success">
                                    $${campaign.total_revenue.toFixed(2)}
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
                        <strong>Период:</strong> ${period.days || 14} дней |
                        <strong>Мин. ROI:</strong> ${params.roi_threshold || 50}% |
                        <strong>Мин. расход в день:</strong> $${params.min_daily_spend || 1.0} |
                        <strong>Макс. волатильность:</strong> ${params.volatility_threshold || 0.3} |
                        <strong>Макс. рост CPC:</strong> ${params.cpc_growth_limit || 20}%
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
        ModuleRegistry.register(ScalingCandidatesModule);
    }
})();
