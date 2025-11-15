// Версия сервис-воркера (обновляй при каждом деплое!)
// Синхронизируй с VERSION файлом в корне проекта
const VERSION = '1.0.4';
const CACHE_NAME = `binom-assistant-v${VERSION}`;

// Ресурсы для кеширования
const STATIC_CACHE_URLS = [
  '/',
  '/static/css/main.css',
  '/static/css/components.css',
  '/static/css/responsive.css',
  '/static/js/chart.min.js',
  '/static/js/api.js',
  '/static/js/notifications.js',
  '/static/js/main.js',
  '/static/images/favicon-96x96.png',
  '/static/images/favicon.svg',
  '/static/images/favicon.ico',
  '/static/images/apple-touch-icon.png',
  '/static/images/web-app-manifest-512x512.png'
];

// Установка service worker
self.addEventListener('install', event => {
  console.log(`[SW] Installing version ${VERSION}`);
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_CACHE_URLS);
      })
      .then(() => {
        console.log('[SW] Installation complete');
        return self.skipWaiting(); // Активировать немедленно
      })
      .catch(error => {
        console.error('[SW] Installation failed:', error);
      })
  );
});

// Активация service worker
self.addEventListener('activate', event => {
  console.log(`[SW] Activating version ${VERSION}`);
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        // Удаляем старые кеши
        return Promise.all(
          cacheNames
            .filter(cacheName => cacheName.startsWith('binom-assistant-') && cacheName !== CACHE_NAME)
            .map(cacheName => {
              console.log(`[SW] Deleting old cache: ${cacheName}`);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => {
        console.log('[SW] Activation complete');
        return self.clients.claim(); // Взять контроль над всеми страницами
      })
  );
});

// Обработка запросов
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Пропускаем не-GET запросы
  if (request.method !== 'GET') {
    return;
  }

  // Пропускаем запросы к chrome-extension и другим схемам
  if (!url.protocol.startsWith('http')) {
    return;
  }

  event.respondWith(
    handleFetch(request, url)
  );
});

async function handleFetch(request, url) {
  // API запросы - всегда с сервера (Network-first)
  if (url.pathname.startsWith('/api/')) {
    try {
      const response = await fetch(request);
      return response;
    } catch (error) {
      console.error('[SW] Network request failed:', error);
      // Можно вернуть кастомную страницу offline
      return new Response(
        JSON.stringify({ error: 'Network error', offline: true }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      );
    }
  }

  // Статические ресурсы - Cache-first
  if (isStaticAsset(url.pathname)) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      // Проверяем версию в фоне и обновляем если нужно
      fetchAndUpdateCache(request);
      return cachedResponse;
    }
    
    // Если нет в кеше - загружаем и кешируем
    try {
      const response = await fetch(request);
      
      if (response.status === 200) {
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, response.clone());
      }
      
      return response;
    } catch (error) {
      console.error('[SW] Failed to fetch:', url.pathname);
      return new Response('Offline', { status: 503 });
    }
  }

  // Все остальное - Network-first
  try {
    return await fetch(request);
  } catch (error) {
    const cachedResponse = await caches.match(request);
    return cachedResponse || new Response('Offline', { status: 503 });
  }
}

// Проверка является ли ресурс статическим
function isStaticAsset(pathname) {
  return pathname.startsWith('/static/') || 
         pathname === '/' ||
         pathname === '/index.html';
}

// Фоновое обновление кеша
async function fetchAndUpdateCache(request) {
  try {
    const response = await fetch(request);
    
    if (response.status === 200) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
  } catch (error) {
    // Игнорируем ошибки фонового обновления
  }
}

// Обработка сообщений от клиента
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => caches.delete(cacheName))
        );
      })
    );
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: VERSION });
  }
});
