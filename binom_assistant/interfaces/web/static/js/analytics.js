/**
 * Логика страницы аналитики
 */

/**
 * Запуск анализа агента
 */
async function runAgent(agentType) {
    try {
        toast.info(`Запуск агента "${agentType}"...`);

        const result = await api.post('/agents/run', {
            agent_type: agentType
        });

        showAnalysisResult(agentType, result);
        toast.success('Анализ завершен');
    } catch (error) {
        console.error('Failed to run agent:', error);
        toast.error('Ошибка запуска агента');
    }
}

/**
 * Показать результат анализа
 */
function showAnalysisResult(agentType, result) {
    const resultContainer = document.getElementById('analysisResult');
    const titleEl = document.getElementById('resultTitle');
    const contentEl = document.getElementById('resultContent');

    if (!resultContainer || !titleEl || !contentEl) return;

    const agentNames = {
        'overview': 'Обзорщик',
        'scanner': 'Сканер',
        'filter': 'Фильтратор',
        'calculator': 'Калькулятор',
        'dynamics': 'Динамик',
        'grouper': 'Группировщик',
        'weekly': 'Недельщик'
    };

    titleEl.textContent = `Результат анализа - ${agentNames[agentType] || agentType}`;
    contentEl.innerHTML = `<pre style="white-space: pre-wrap; font-size: 0.875rem; line-height: 1.6;">${result.analysis || 'Нет данных'}</pre>`;

    resultContainer.style.display = 'block';
}

/**
 * Обработчики событий
 */
function initAnalyticsPage() {
    // Агенты
    const agentCards = document.querySelectorAll('.agent-card');
    agentCards.forEach(card => {
        card.addEventListener('click', () => {
            const agentType = card.dataset.agent;
            runAgent(agentType);
        });
    });

    // Закрытие результата
    const closeBtn = document.getElementById('closeResult');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('analysisResult').style.display = 'none';
        });
    }
}

// Инициализация при загрузке страницы
if (window.location.pathname.includes('/analytics')) {
    document.addEventListener('DOMContentLoaded', initAnalyticsPage);
}
