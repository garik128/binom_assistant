/**
 * Реестр модулей аналитики
 */
const ModuleRegistry = {
    modules: {},

    /**
     * Регистрация модуля
     * @param {Object} module - Объект модуля
     */
    register(module) {
        if (!module.id) {
            console.error('Module must have an id:', module);
            return;
        }
        this.modules[module.id] = module;
        console.log(`Module registered: ${module.id}`);
    },

    /**
     * Получение модуля по ID
     * @param {string} moduleId - ID модуля
     * @returns {Object|null} - Объект модуля или null
     */
    get(moduleId) {
        return this.modules[moduleId] || null;
    },

    /**
     * Получение всех модулей
     * @returns {Object} - Все модули
     */
    getAll() {
        return this.modules;
    }
};

// Экспорт для использования в других файлах
if (typeof window !== 'undefined') {
    window.ModuleRegistry = ModuleRegistry;
}
