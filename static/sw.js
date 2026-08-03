/* Service Worker for AltaJobs - simple precache + runtime caching */
const PRECACHE = 'altajobs-shell-v1';
const RUNTIME = 'altajobs-runtime-v1';

const PRECACHE_URLS = [
  '/',
  '/static/offline.html',
  '/static/css/styles.css',
  '/static/css/style.css',
  '/static/css/jobs.css',
  '/static/css/feed.css',
  '/static/js/app.js',
  '/static/js/jobs-page.js',
  '/static/js/feed.js',
  '/static/js/ui-components.js',
  '/static/images/logo-192.png',
  '/static/images/logo-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PRECACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  const currentCaches = [PRECACHE, RUNTIME];
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => !currentCaches.includes(key)).map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Utility: return offline response for navigations
function offlineResponse(){
  return caches.match('/static/offline.html');
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Always handle navigation requests with cache-first, fallback to offline
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(response => {
        // update cache with latest navigation response
        const copy = response.clone();
        caches.open(RUNTIME).then(cache => cache.put(request, copy));
        return response;
      }).catch(() => caches.match(request).then(r => r || offlineResponse()))
    );
    return;
  }

  // Network-first for API or feed routes (dynamic)
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/feed') || request.headers.get('accept') && request.headers.get('accept').includes('application/json')) {
    event.respondWith(
      fetch(request).then(response => {
        // cache a copy
        const copy = response.clone();
        caches.open(RUNTIME).then(cache => cache.put(request, copy));
        return response;
      }).catch(() => caches.match(request).then(r => r || offlineResponse()))
    );
    return;
  }

  // For other requests (assets): try cache first, then network
  event.respondWith(
    caches.match(request).then(cached => cached || fetch(request).then(response => {
      // optionally cache runtime assets
      return caches.open(RUNTIME).then(cache => { cache.put(request, response.clone()); return response; });
    })).catch(() => caches.match('/static/offline.html'))
  );
});
