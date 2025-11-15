/**
 * Модуль: Оценка рисков (Risk Assessment)
 * Выявляет и квантифицирует риски портфеля
 */
(function() {
    const RiskAssessmentModule = {
        id: 'risk_assessment',

        translations: {
            risk_score: 'Оценка риска',
            risk_level: 'Уровень риска',
            total_campaigns: 'Всего кампаний',
            total_cost: 'Общий расход ($)',
            total_revenue: 'Общий доход ($)',
            total_pending_leads: 'Pending лидов',
            concentration_risk: 'Риск концентрации',
            volatility_risk: 'Риск волатильности',
            liquidity_risk: 'Риск ликвидности',
            operational_risk: 'Операционный риск',
            roi_std_dev: 'Стандартное отклонение ROI',
            max_source_revenue_share: 'Макс. доля источника (%)'
        },

        algorithm: `
            <ol>
                <li>Загрузка данных по всем кампаниям за период</li>
                <li>Фильтрация шума (расход < 1$ или клики < 50)</li>
                <li>Расчет компонентов риска:
                    <ol>
                        <li><strong>Риск концентрации</strong>:
                            <ul>
                                <li>Оценивает зависимость от одного источника доходов</li>
                                <li>< 30% доли -> score 0 (низкий риск)</li>
                                <li>50% доли -> score 50 (средний риск)</li>
                                <li>> 70% доли -> score 100 (критический риск)</li>
                            </ul>
                        </li>
                        <li><strong>Риск волатильности</strong>:
                            <ul>
                                <li>Коэффициент вариации ROI кампаний</li>
                                <li>CV = std_dev(roi_values) / abs(mean(roi_values))</li>
                                <li>CV = 0 -> score 0 (низкий риск)</li>
                                <li>CV = 1.0+ -> score 100 (высокий риск)</li>
                            </ul>
                        </li>
                        <li><strong>Риск ликвидности</strong>:
                            <ul>
                                <li>Оценка потенциального доходаот pending лидов</li>
                                <li>< 10 pending на $1 дохода -> score 0</li>
                                <li>> 100 pending на $1 дохода -> score 100</li>
                            </ul>
                        </li>
                        <li><strong>Операционный риск</strong>:
                            <ul>
                                <li>Зависимость от одной группы кампаний</li>
                                <li>HHI = sum(group_share^2)</li>
                                <li>HHI = 0 -> score 0 (диверсифицировано)</li>
                                <li>HHI = 1 -> score 100 (одна группа)</li>
                            </ul>
                        </li>
                    </ol>
                </li>
                <li>Расчет общей оценки риска:
                    <ul>
                        <li>risk_score = (concentration + volatility + liquidity + operational) / 4</li>
                        <li>Чем выше score, тем выше риск портфеля</li>
                    </ul>
                </li>
            </ol>
        `,

        metrics: `
            <li><strong>Risk Score</strong> - общая оценка риска портфеля (0-100, чем выше = больше риск)</li>
            <li><strong>Risk Level</strong> - уровень риска (low/medium/high/critical)</li>
            <li><strong>Concentration Risk</strong> - риск зависимости от одного источника доходов</li>
            <li><strong>Volatility Risk</strong> - риск высокой дисперсии ROI кампаний</li>
            <li><strong>Liquidity Risk</strong> - риск из-за больших pending апрувов</li>
            <li><strong>Operational Risk</strong> - риск зависимости от одной группы кампаний</li>
            <li><strong>Total Campaigns</strong> - количество анализируемых кампаний</li>
            <li><strong>Total Pending Leads</strong> - общее количество неаппрувленных лидов</li>
            <li><strong>ROI Standard Deviation</strong> - волатильность ROI по кампаниям</li>
        `,

        paramTranslations: {
            days: 'Период анализа (дней)',
            min_cost: 'Минимальный расход ($)',
            min_leads: 'Минимум лидов',
            high_concentration_threshold: 'Порог концентрации (%)'
        },

        renderTable: function(results, container) {
            if (!results.data) {
                container.innerHTML = '<p class="text-muted">Нет данных для отображения</p>';
                return;
            }

            const data = results.data;
            const risks = data.risks || {};
            const summary = data.summary || {};
            const period = data.period || {};
            const riskScore = data.risk_score || 0;
            const riskLevel = data.risk_level || 'medium';

            // Определяем статус и цвет
            let statusColor, statusText, statusBg;
            if (riskLevel === 'low') {
                statusColor = '#28a745';
                statusText = 'Низкий';
                statusBg = 'rgba(40, 167, 69, 0.1)';
            } else if (riskLevel === 'medium') {
                statusColor = '#17a2b8';
                statusText = 'Средний';
                statusBg = 'rgba(23, 162, 184, 0.1)';
            } else if (riskLevel === 'high') {
                statusColor = '#ffc107';
                statusText = 'Высокий';
                statusBg = 'rgba(255, 193, 7, 0.1)';
            } else {
                statusColor = '#dc3545';
                statusText = 'Критический';
                statusBg = 'rgba(220, 53, 69, 0.1)';
            }

            let html = '';

            // Главная оценка риска
            html += `
                <div class="risk-assessment-container" style="background: ${statusBg}; border-left: 4px solid ${statusColor}; padding: 20px; margin-bottom: 20px; border-radius: 4px;">
                    <div class="row">
                        <div class="col-md-4 text-center">
                            <div class="risk-assessment-display">
                                <div class="risk-score-value" style="color: ${statusColor};">
                                    <span style="font-size: 48px; font-weight: bold;">${riskScore.toFixed(1)}</span>
                                    <span class="text-muted" style="font-size: 20px;"> / 100</span>
                                </div>
                                <div style="font-size: 16px; color: ${statusColor}; font-weight: bold; margin-top: 8px;">
                                    ${statusText}
                                </div>
                            </div>
                        </div>
                        <div class="col-md-8">
                            <div class="risks-grid">
                                <div class="risk-item">
                                    <div class="risk-label">Концентрация</div>
                                    <div class="risk-value">${risks.concentration_risk ? risks.concentration_risk.toFixed(1) : 0}</div>
                                    <div class="risk-bar">
                                        <div class="risk-fill" style="width: ${Math.min(risks.concentration_risk || 0, 100)}%; background: #dc3545;"></div>
                                    </div>
                                </div>
                                <div class="risk-item">
                                    <div class="risk-label">Волатильность</div>
                                    <div class="risk-value">${risks.volatility_risk ? risks.volatility_risk.toFixed(1) : 0}</div>
                                    <div class="risk-bar">
                                        <div class="risk-fill" style="width: ${Math.min(risks.volatility_risk || 0, 100)}%; background: #fd7e14;"></div>
                                    </div>
                                </div>
                                <div class="risk-item">
                                    <div class="risk-label">Ликвидность</div>
                                    <div class="risk-value">${risks.liquidity_risk ? risks.liquidity_risk.toFixed(1) : 0}</div>
                                    <div class="risk-bar">
                                        <div class="risk-fill" style="width: ${Math.min(risks.liquidity_risk || 0, 100)}%; background: #ffc107;"></div>
                                    </div>
                                </div>
                                <div class="risk-item">
                                    <div class="risk-label">Операционный</div>
                                    <div class="risk-value">${risks.operational_risk ? risks.operational_risk.toFixed(1) : 0}</div>
                                    <div class="risk-bar">
                                        <div class="risk-fill" style="width: ${Math.min(risks.operational_risk || 0, 100)}%; background: #6f42c1;"></div>
                                    </div>
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

            // Добавляем стили для компонентов
            this.injectStyles();
        },

        injectStyles: function() {
            if (document.getElementById('risk-assessment-styles')) {
                return;
            }

            const style = document.createElement('style');
            style.id = 'risk-assessment-styles';
            style.textContent = `
                .risk-assessment-container {
                    border-radius: 8px;
                }

                .risk-assessment-display {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                }

                .risk-score-value {
                    text-align: center;
                }

                .risks-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 12px;
                }

                .risk-item {
                    background: #1a1a1a;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 10px;
                }

                .risk-label {
                    font-size: 11px;
                    font-weight: 500;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 6px;
                }

                .risk-value {
                    font-size: 18px;
                    font-weight: bold;
                    margin-bottom: 6px;
                }

                .risk-bar {
                    width: 100%;
                    height: 6px;
                    background: #e9ecef;
                    border-radius: 3px;
                    overflow: hidden;
                }

                .risk-fill {
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
                    .risk-assessment-container .row {
                        flex-direction: column;
                    }

                    .risks-grid {
                        grid-template-columns: repeat(2, 1fr);
                    }
                }
            `;

            document.head.appendChild(style);
        }
    };

    // Регистрируем модуль
    if (typeof ModuleRegistry !== 'undefined') {
        ModuleRegistry.register(RiskAssessmentModule);
    }
})();
