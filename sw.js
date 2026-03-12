const CACHE_NAME = 'ai-news-v11';
const ASSETS = [
  './',
  './index.html',
  './install.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

// 설치 시 필수 자원 캐싱
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('SW: Caching assets');
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.map(k => {
        if (k !== CACHE_NAME) {
          console.log('SW: Deleting old cache', k);
          return caches.delete(k);
        }
      })
    ))
  );
  self.clients.claim();
});

// Network First, Falling back to Cache
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  
  e.respondWith(
    fetch(e.request)
      .catch(() => {
        return caches.match(e.request);
      })
  );
});
