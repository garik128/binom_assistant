/**
 * API клиент для работы с бэкендом
 */

const API_BASE = '/api/v1';

const api = {
    /**
     * Получить заголовки с токеном авторизации
     * @returns {object}
     */
    getAuthHeaders() {
        const token = localStorage.getItem('access_token');
        const headers = {
            'Content-Type': 'application/json'
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        return headers;
    },

    /**
     * Проверить, что пользователь авторизован
     * @returns {boolean}
     */
    isAuthenticated() {
        return !!localStorage.getItem('access_token');
    },

    /**
     * GET запрос к API
     * @param {string} endpoint - путь к endpoint
     * @param {number} timeout - таймаут запроса в миллисекундах (по умолчанию 30000)
     * @returns {Promise<any>}
     */
    async get(endpoint, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                signal: controller.signal,
                headers: this.getAuthHeaders()
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                // Если 401 или 403 (Forbidden) - редирект на логин
                if (response.status === 401 || response.status === 403) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/api/v1/auth/login';
                    return;
                }

                let errorMessage = `API Error: ${response.status} ${response.statusText}`;
                try {
                    const errorBody = await response.json();
                    if (errorBody.detail) {
                        errorMessage = errorBody.detail;
                    }
                } catch (e) {
                    // Response body is not JSON, use default message
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('Request timeout');
            }
            // Не логируем ошибки соединения для health checks (они обрабатываются в вызывающем коде)
            if (!endpoint.includes('/health')) {
                console.error('API GET Error:', error);
            }
            throw error;
        }
    },

    /**
     * POST запрос к API
     * @param {string} endpoint - путь к endpoint
     * @param {object} data - данные для отправки
     * @param {number} timeout - таймаут запроса в миллисекундах (по умолчанию 30000)
     * @returns {Promise<any>}
     */
    async post(endpoint, data, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify(data),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                // Если 401 или 403 (Forbidden) - редирект на логин
                if (response.status === 401 || response.status === 403) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/api/v1/auth/login';
                    return;
                }

                let errorMessage = `API Error: ${response.status} ${response.statusText}`;
                try {
                    const errorBody = await response.json();
                    if (errorBody.detail) {
                        errorMessage = errorBody.detail;
                    }
                } catch (e) {
                    // Response body is not JSON, use default message
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                console.error('API POST Timeout:', endpoint);
                throw new Error('Request timeout');
            }
            console.error('API POST Error:', error);
            throw error;
        }
    },

    /**
     * PUT запрос к API
     * @param {string} endpoint - путь к endpoint
     * @param {object} data - данные для отправки
     * @param {number} timeout - таймаут запроса в миллисекундах (по умолчанию 30000)
     * @returns {Promise<any>}
     */
    async put(endpoint, data, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'PUT',
                headers: this.getAuthHeaders(),
                body: JSON.stringify(data),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                // Если 401 или 403 (Forbidden) - редирект на логин
                if (response.status === 401 || response.status === 403) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/api/v1/auth/login';
                    return;
                }

                let errorMessage = `API Error: ${response.status} ${response.statusText}`;
                try {
                    const errorBody = await response.json();
                    if (errorBody.detail) {
                        errorMessage = errorBody.detail;
                    }
                } catch (e) {
                    // Response body is not JSON, use default message
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                console.error('API PUT Timeout:', endpoint);
                throw new Error('Request timeout');
            }
            console.error('API PUT Error:', error);
            throw error;
        }
    },

    /**
     * DELETE запрос к API
     * @param {string} endpoint - путь к endpoint
     * @param {number} timeout - таймаут запроса в миллисекундах (по умолчанию 30000)
     * @returns {Promise<any>}
     */
    async delete(endpoint, timeout = 30000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'DELETE',
                headers: this.getAuthHeaders(),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                // Если 401 или 403 (Forbidden) - редирект на логин
                if (response.status === 401 || response.status === 403) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/api/v1/auth/login';
                    return;
                }

                let errorMessage = `API Error: ${response.status} ${response.statusText}`;
                try {
                    const errorBody = await response.json();
                    if (errorBody.detail) {
                        errorMessage = errorBody.detail;
                    }
                } catch (e) {
                    // Response body is not JSON, use default message
                }
                throw new Error(errorMessage);
            }
            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                console.error('API DELETE Timeout:', endpoint);
                throw new Error('Request timeout');
            }
            console.error('API DELETE Error:', error);
            throw error;
        }
    }
};

// Экспортируем для использования в других модулях
window.api = api;
