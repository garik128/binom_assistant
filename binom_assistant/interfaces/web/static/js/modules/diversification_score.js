/**
 * Модуль: Диверсификация (Diversification Score)
 * Оценивает диверсификацию рисков портфеля на основе HHI и распределения
 */
(function() {
    const DiversificationScoreModule = {
        id: 'diversification_score',

        translations: {
            diversification_score: 'Индекс диверсификации',
            diversification_level: 'Уровень диверсификации',
            hhi_sources: 'HHI источников',
            herfindahl_index: 'Индекс Херфиндаля',
            top_source_share: 'Доля топ источника (%)',
            top_group_share: 'Доля топ группы (%)',
            cpl_cpa_balance: 'Баланс CPA (%)',
            risk_level: 'Уровень риска',
            unique_sources: 'Уникальных источников',
            unique_groups: 'Уникальных групп',
            cpa_campaigns: 'CPA кампаний',
            cpl_campaigns: 'CPL кампаний',
            total_campaigns: 'Всего кампаний',
            total_cost: 'Общий расход ($)',
            total_revenue: 'Общий доход ($)'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Фильтрация шума (расход < 1$ или клики < 50)</li>
                <li>Расчет метрик диверсификации:
                    <ol>
                        <li><strong>Индекс Херфиндаля-Хиршмана (HHI) источников</strong>:
                            <ul>
                                <li>HHI = сумма (доля_источника ^ 2)</li>
                                <li>HHI от 0 (идеальная диверсификация) до 1 (полная концентрация)</li>
                            </ul>
                        </li>
                        <li><strong>Доля топ источника</strong>:
                            <ul>
                                <li>Процент расходов самого большого источника</li>
                                <li>Идеально < 30%</li>
                            </ul>
                        </li>
                        <li><strong>Доля топ группы</strong>:
                            <ul>
                                <li>Процент расходов самой большой группы</li>
                                <li>Идеально < 30%</li>
                            </ul>
                        </li>
                        <li><strong>Баланс CPL vs CPA</strong>:
                            <ul>
                                <li>Процент CPA кампаний в портфеле</li>
                                <li>Идеально близко к 50%</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет общего индекса диверсификации (0-100):
                    <ul>
                        <li>HHI score (30%): (1 - HHI) * 100</li>
                        <li>Top source score (25%): штраф если > 30%</li>
                        <li>Top group score (25%): штраф если > 30%</li>
                        <li>Balance score (20%): максимум при 50%</li>
                    </ul>
                </li>
                <li>Определение уровня риска (low/medium/high)</li>
            </ol>
        `,

        metrics: `
            <li><strong>Diversification Score</strong> - общий индекс диверсификации (0-100)</li>
            <li><strong>HHI Sources</strong> - индекс Херфиндаля-Хиршмана для источников (0-1, чем ниже тем лучше)</li>
            <li><strong>Top Source Share</strong> - процент расходов самого крупного источника (%)</li>
            <li><strong>Top Group Share</strong> - процент расходов самой крупной группы (%)</li>
            <li><strong>CPL/CPA Balance</strong> - процент CPA кампаний (% CPA)</li>
            <li><strong>Risk Level</strong> - уровень риска концентрации (low/medium/high)</li>
            <li><strong>Unique Sources</strong> - количество уникальных источников трафика</li>
            <li><strong>Unique Groups</strong> - количество уникальных групп кампаний</li>
            <li><strong>Total Cost</strong> - общий расход портфеля ($)</li>
            <li><strong>Total Revenue</strong> - общий доход портфеля ($)</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cost: 'Минимальный расход ($)',
            min_leads: 'Минимум лидов',
            max_single_source_share: 'Макс. доля источника (%)',
            max_single_group_share: 'Макс. доля группы (%)',
            hhi_threshold: 'Порог HHI',
            critical_source_share: 'Критическая доля источника (%)'
        },

        renderTable: function(results, container) {
            if (!results.data) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const diversificationScore = data.diversification_score || 0;
            const riskLevel = data.risk_level || 'unknown';
            const hhi = data.hhi_sources || 0;
            const topSourceShare = data.top_source_share || 0;
            const topGroupShare = data.top_group_share || 0;
            const cplCpaBalance = data.cpl_cpa_balance || 50;
            const summary = data.summary || {};
            const period = data.period || {};

            // Определяем цвета и статусы
            let statusColor, statusText, statusBg;
            if (diversificationScore >= 70) {
                statusColor = '#28a745';
                statusText = 'Отличная';
                statusBg = 'rgba(40, 167, 69, 0.1)';
            } else if (diversificationScore >= 50) {
                statusColor = '#17a2b8';
                statusText = 'Хорошая';
                statusBg = 'rgba(23, 162, 184, 0.1)';
            } else if (diversificationScore >= 30) {
                statusColor = '#ffc107';
                statusText = 'Средняя';
                statusBg = 'rgba(255, 193, 7, 0.1)';
            } else {
                statusColor = '#dc3545';
                statusText = 'Низкая';
                statusBg = 'rgba(220, 53, 69, 0.1)';
            }

            // Цвет для риска
            let riskColor, riskText;
            if (riskLevel === 'low') {
                riskColor = '#28a745';
                riskText = 'Низкий';
            } else if (riskLevel === 'medium') {
                riskColor = '#ffc107';
                riskText = 'Средний';
            } else if (riskLevel === 'high') {
                riskColor = '#dc3545';
                riskText = 'Высокий';
            } else {
                riskColor = '#999';
                riskText = 'Неизвестный';
            }

            let html = '';

            // Главный индекс диверсификации
            html += `
                <div class="diversification-container" style="background: ${statusBg}; border-left: 4px solid ${statusColor}; padding: 20px; margin-bottom: 20px; border-radius: 4px;">
                    <div class="row">
                        <div class="col-md-4 text-center">
                            <div class="diversification-display">
                                <div class="diversification-value" style="color: ${statusColor};">
                                    <span style="font-size: 48px; font-weight: bold;">${diversificationScore.toFixed(1)}</span>
                                    <span class="text-muted" style="font-size: 20px;"> / 100</span>
                                </div>
                                <div style="font-size: 16px; color: ${statusColor}; font-weight: bold; margin-top: 8px;">
                                    ${statusText} диверсификация
                                </div>
                                <div style="font-size: 13px; color: ${riskColor}; font-weight: 500; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1);">
                                    Риск: ${riskText}
                                </div>
                            </div>
                        </div>
                        <div class="col-md-8">
                            <div class="metrics-grid">
                                <div class="metric-item">
                                    <div class="metric-label">HHI источников</div>
                                    <div class="metric-value" style="color: ${hhi < 0.25 ? '#28a745' : hhi < 0.5 ? '#ffc107' : '#dc3545'};">
                                        ${hhi.toFixed(4)}
                                    </div>
                                    <div class="metric-hint">чем ниже, тем лучше</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-label">Доля топ источника</div>
                                    <div class="metric-value" style="color: ${topSourceShare < 30 ? '#28a745' : topSourceShare < 40 ? '#ffc107' : '#dc3545'};">
                                        ${topSourceShare.toFixed(1)}%
                                    </div>
                                    <div class="metric-hint">идеально < 30%</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-label">Доля топ группы</div>
                                    <div class="metric-value" style="color: ${topGroupShare < 30 ? '#28a745' : topGroupShare < 40 ? '#ffc107' : '#dc3545'};">
                                        ${topGroupShare.toFixed(1)}%
                                    </div>
                                    <div class="metric-hint">идеально < 30%</div>
                                </div>
                                <div class="metric-item">
                                    <div class="metric-label">Баланс CPA/CPL</div>
                                    <div class="metric-value" style="color: ${Math.abs(cplCpaBalance - 50) < 20 ? '#28a745' : Math.abs(cplCpaBalance - 50) < 40 ? '#ffc107' : '#dc3545'};">
                                        ${cplCpaBalance.toFixed(1)}%
                                    </div>
                                    <div class="metric-hint">CPA кампаний</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Info banner (summary отрисовывается отдельно в resultsSummary)
            html += `
                <div class="info-banner">
                    <strong>Период:</strong> ${period.days || 7} дней (${period.date_from || 'N/A'} - ${period.date_to || 'N/A'})
                </div>
            `;

            container.innerHTML = html;
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(DiversificationScoreModule);
    }
})();
