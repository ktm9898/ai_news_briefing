const CACHE_NAME = 'ai-news-vs-v5';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json'
];

self.addEventListener('install', (event) => {
  console.log('SW v5 Installing');
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        // 개별적으로 추가하여 하나가 실패해도 설치는 되도록 시도 (addAll 대신 개별 처리)
        return Promise.allSettled(
          ASSETS_TO_CACHE.map(url => cache.add(url).catch(err => console.warn('Cache add failed for:', url, err)))
        );
      })
  );
});

self.addEventListener('activate', (event) => {
  console.log('SW v5 Activating');
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((key) => {
        if (key !== CACHE_NAME) return caches.delete(key);
      }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
