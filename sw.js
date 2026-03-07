const CACHE_NAME = 'ai-news-briefing-v1';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  'https://cdn.tailwindcss.com',
  'https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css'
];

// 설치 이벤트
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(ASSETS_TO_CACHE))
      .then(() => self.skipWaiting())
  );
});

// 활성화 이벤트
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// 페치 이벤트 (네트워크 우선, 실패 시 캐시)
self.addEventListener('fetch', (event) => {
  // API 요청 등은 캐싱 전략에서 제외하거나 별도 처리 가능
  if (event.request.url.includes('script.google.com')) {
    return; // GAS 호출은 브라우저 기본 fetch에 위임
  }
  
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // 성공 시 캐시 업데이트
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseClone);
        });
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
