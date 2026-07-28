const CACHE_NAME = 'revac-field-v1';
const ASSETS = [
  '/m',
  '/m/',
  '/mobile/index.html',
  '/mobile/app.js',
  '/mobile/manifest.json'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.map(k => {
        if (k !== CACHE_NAME) return caches.delete(k);
      })
    ))
  );
});

self.addEventListener('fetch', e => {
  // Pass API requests through to the network
  if (e.request.url.includes('/api/')) {
    return;
  }
  
  e.respondWith(
    caches.match(e.request).then(cached => {
      return cached || fetch(e.request).then(response => {
        return caches.open(CACHE_NAME).then(cache => {
          cache.put(e.request, response.clone());
          return response;
        });
      });
    }).catch(() => {
      // Fallback if offline and resource not cached
      if (e.request.mode === 'navigate') {
        return caches.match('/mobile/index.html');
      }
    })
  );
});
