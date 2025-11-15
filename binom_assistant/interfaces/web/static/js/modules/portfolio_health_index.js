/**
 * Модуль: Здоровье портфеля (Portfolio Health Index)
 * Рассчитывает общий индекс здоровья портфеля кампаний от 0 до 100
 */
(function() {
    const PortfolioHealthIndexModule = {
        id: 'portfolio_health_index',

        translations: {
            health_index: 'Индекс здоровья',
            total_campaigns: 'Всего кампаний',
            profitable_campaigns: 'Прибыльных кампаний',
            avg_roi: 'Средний ROI (%)',
            total_cost: 'Общий расход ($)',
            total_revenue: 'Общий доход ($)',
            weighted_roi: 'Средневзвешенный ROI',
            profitable_ratio: 'Доля прибыльных',
            profitable_campaigns_ratio: 'Доля прибыльных кампаний',
            portfolio_stability: 'Стабильность портфеля',
            diversification_level: 'Уровень диверсификации',
            trend_direction: 'Направление тренда',
            stability: 'Стабильность',
            diversification: 'Диверсификация',
            trend: 'Тренд'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Фильтрация шума (расход < 1$ или клики < 50)</li>
                <li>Расчет компонентов индекса:
                    <ol>
                        <li><strong>Средневзвешенный ROI (30%)</strong>:
                            <ul>
                                <li>ROI = ((revenue - cost) / cost) * 100</li>
                                <li>weighted_roi = sum(campaign_roi * campaign_cost) / total_cost</li>
                                <li>score = max(0, min(100, 50 + weighted_roi/2))</li>
                            </ul>
                        </li>
                        <li><strong>Доля прибыльных кампаний (25%)</strong>:
                            <ul>
                                <li>profitable_campaigns = count(revenue > cost)</li>
                                <li>score = (profitable_campaigns / total_campaigns) * 100</li>
                            </ul>
                        </li>
                        <li><strong>Стабильность метрик (20%)</strong>:
                            <ul>
                                <li>CV = std_dev(roi_values) / abs(mean(roi_values))</li>
                                <li>score = max(0, 100 * (1 - CV))</li>
                            </ul>
                        </li>
                        <li><strong>Диверсификация (15%)</strong>:
                            <ul>
                                <li>HHI = sum(group_share^2) для всех групп</li>
                                <li>score = (1 - HHI) * 100</li>
                            </ul>
                        </li>
                        <li><strong>Тренд последних 7 дней (10%)</strong>:
                            <ul>
                                <li>Сравнение ROI первой и второй половины периода</li>
                                <li>trend_pct = ((second_half - first_half) / first_half) * 100</li>
                                <li>score = max(0, min(100, 50 + trend_pct/2))</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет общего индекса:
                    <ul>
                        <li>health_index = weighted_roi*0.30 + profitable_ratio*0.25 + stability*0.20 + diversification*0.15 + trend*0.10</li>
                    </ul>
                </li>
            </ol>
        `,

        metrics: `
            <li><strong>Health Index</strong> - общий индекс здоровья портфеля (0-100)</li>
            <li><strong>Weighted ROI Score</strong> - взвешенный ROI в масштабе 0-100</li>
            <li><strong>Profitable Ratio Score</strong> - процент прибыльных кампаний</li>
            <li><strong>Stability Score</strong> - стабильность метрик (низкая волатильность = высокий score)</li>
            <li><strong>Diversification Score</strong> - диверсификация портфеля по группам (Индекс Герфиндаля)</li>
            <li><strong>Trend Score</strong> - тренд последних дней (положительный тренд = высокий score)</li>
            <li><strong>Total Campaigns</strong> - количество анализируемых кампаний</li>
            <li><strong>Profitable Campaigns</strong> - количество прибыльных кампаний</li>
            <li><strong>Average ROI</strong> - средний ROI по портфелю (%)</li>
            <li><strong>Total Cost</strong> - общий расход портфеля ($)</li>
            <li><strong>Total Revenue</strong> - общий доход портфеля ($)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cost: 'Минимальный расход ($)',
            min_leads: 'Минимум лидов',
            roi_weight: 'Вес ROI (%)',
            profitable_weight: 'Вес прибыльности (%)',
            stability_weight: 'Вес стабильности (%)',
            diversification_weight: 'Вес диверсификации (%)',
            trend_weight: 'Вес тренда (%)'
        },

        renderTable: function(results, container) {
            if (!results.data) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const components = data.components || {};
            const summary = data.summary || {};
            const period = data.period || {};
            const healthIndex = data.health_index || 0;

            // Определяем статус и цвет
            let statusColor, statusText, statusBg;
            if (healthIndex >= 80) {
                statusColor = '#28a745';
                statusText = 'Отличное';
                statusBg = 'rgba(40, 167, 69, 0.1)';
            } else if (healthIndex >= 60) {
                statusColor = '#17a2b8';
                statusText = 'Хорошее';
                statusBg = 'rgba(23, 162, 184, 0.1)';
            } else if (healthIndex >= 40) {
                statusColor = '#ffc107';
                statusText = 'Среднее';
                statusBg = 'rgba(255, 193, 7, 0.1)';
            } else {
                statusColor = '#dc3545';
                statusText = 'Плохое';
                statusBg = 'rgba(220, 53, 69, 0.1)';
            }

            let html = '';

            // Главный индекс здоровья
            html += `
                <div class="health-index-container" style="background: ${statusBg}; border-left: 4px solid ${statusColor}; padding: 20px; margin-bottom: 20px; border-radius: 4px;">
                    <div class="row">
                        <div class="col-md-4 text-center">
                            <div class="health-index-display">
                                <div class="health-index-value" style="color: ${statusColor};">
                                    <span style="font-size: 48px; font-weight: bold;">${healthIndex.toFixed(1)}</span>
                                    <span class="text-muted" style="font-size: 20px;"> / 100</span>
                                </div>
                                <div style="font-size: 16px; color: ${statusColor}; font-weight: bold; margin-top: 8px;">
                                    ${statusText}
                                </div>
                            </div>
                        </div>
                        <div class="col-md-8">
                            <div class="components-grid">
                                <div class="component-item">
                                    <div class="component-label">ROI (30%)</div>
                                    <div class="component-value">${components.weighted_roi ? components.weighted_roi.toFixed(1) : 0}</div>
                                    <div class="component-bar">
                                        <div class="component-fill" style="width: ${Math.min(components.weighted_roi || 0, 100)}%; background: #0d6efd;"></div>
                                    </div>
                                </div>
                                <div class="component-item">
                                    <div class="component-label">Прибыльность (25%)</div>
                                    <div class="component-value">${components.profitable_ratio ? components.profitable_ratio.toFixed(1) : 0}</div>
                                    <div class="component-bar">
                                        <div class="component-fill" style="width: ${Math.min(components.profitable_ratio || 0, 100)}%; background: #28a745;"></div>
                                    </div>
                                </div>
                                <div class="component-item">
                                    <div class="component-label">Стабильность (20%)</div>
                                    <div class="component-value">${components.stability ? components.stability.toFixed(1) : 0}</div>
                                    <div class="component-bar">
                                        <div class="component-fill" style="width: ${Math.min(components.stability || 0, 100)}%; background: #17a2b8;"></div>
                                    </div>
                                </div>
                                <div class="component-item">
                                    <div class="component-label">Диверсификация (15%)</div>
                                    <div class="component-value">${components.diversification ? components.diversification.toFixed(1) : 0}</div>
                                    <div class="component-bar">
                                        <div class="component-fill" style="width: ${Math.min(components.diversification || 0, 100)}%; background: #ffc107;"></div>
                                    </div>
                                </div>
                                <div class="component-item">
                                    <div class="component-label">Тренд (10%)</div>
                                    <div class="component-value">${components.trend ? components.trend.toFixed(1) : 0}</div>
                                    <div class="component-bar">
                                        <div class="component-fill" style="width: ${Math.min(components.trend || 0, 100)}%; background: #6f42c1;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Summary статистика
            html += `
                <div class="summary-grid">
                    <div class="summary-card">
                        <div class="summary-label">Всего кампаний</div>
                        <div class="summary-value">${summary.total_campaigns || 0}</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-label">Прибыльных</div>
                        <div class="summary-value text-success">
                            ${summary.profitable_campaigns || 0}
                            <span class="text-muted" style="font-size: 12px;">
                                (${summary.total_campaigns ? ((summary.profitable_campaigns / summary.total_campaigns) * 100).toFixed(1) : 0}%)
                            </span>
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-label">Средний ROI</div>
                        <div class="summary-value ${(summary.avg_roi || 0) >= 0 ? 'text-success' : 'text-danger'}">
                            ${summary.avg_roi ? summary.avg_roi.toFixed(1) : 0}%
                        </div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-label">Общий расход</div>
                        <div class="summary-value">$${summary.total_cost ? summary.total_cost.toFixed(2) : '0.00'}</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-label">Общий доход</div>
                        <div class="summary-value text-success">$${summary.total_revenue ? summary.total_revenue.toFixed(2) : '0.00'}</div>
                    </div>
                    <div class="summary-card">
                        <div class="summary-label">Прибыль</div>
                        <div class="summary-value ${((summary.total_revenue || 0) - (summary.total_cost || 0)) >= 0 ? 'text-success' : 'text-danger'}">
                            $${((summary.total_revenue || 0) - (summary.total_cost || 0)).toFixed(2)}
                        </div>
                    </div>
                </div>
            `;

            // Info banner
            html += `
                <div class="info-banner">
                    <strong>Период:</strong> ${period.days || 7} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
                </div>
            `;

            container.innerHTML = html;

            // Добавляем стили для компонентов
            this.injectStyles();
        },

        injectStyles: function() {
            if (document.getElementById('portfolio-health-styles')) {
                return;
            }

            const style = document.createElement('style');
            style.id = 'portfolio-health-styles';
            style.textContent = `
                .health-index-container {
                    border-radius: 8px;
                }

                .health-index-display {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                }

                .health-index-value {
                    text-align: center;
                }

                .components-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 12px;
                }

                .component-item {
                    background: #1a1a1a;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 10px;
                }

                .component-label {
                    font-size: 11px;
                    font-weight: 500;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 6px;
                }

                .component-value {
                    font-size: 18px;
                    font-weight: bold;
                    margin-bottom: 6px;
                }

                .component-bar {
                    width: 100%;
                    height: 6px;
                    background: #e9ecef;
                    border-radius: 3px;
                    overflow: hidden;
                }

                .component-fill {
                    height: 100%;
                    transition: width 0.3s ease;
                }

                .summary-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 12px;
                    margin: 20px 0;
                }

                .summary-card {
                    background: #1a1a1a;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 12px;
                    text-align: center;
                }

                .summary-label {
                    font-size: 12px;
                    margin-bottom: 6px;
                    font-weight: 500;
                }

                .summary-value {
                    font-size: 20px;
                    font-weight: bold;
                }

                .info-banner {
                    background: #1a1a1a;
                    border-left: 3px solid #0d6efd;
                    padding: 12px;
                    margin-top: 20px;
                    border-radius: 4px;
                    font-size: 13px;
                }

                @media (max-width: 768px) {
                    .health-index-container .row {
                        flex-direction: column;
                    }

                    .components-grid {
                        grid-template-columns: repeat(2, 1fr);
                    }
                }
            `;

            document.head.appendChild(style);
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(PortfolioHealthIndexModule);
    }
})();
