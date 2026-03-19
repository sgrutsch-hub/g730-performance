const CACHE = 'swingdoctor-v5';
const ASSETS = ['./', 'index.html', 'manifest.json', 'apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;

  // Network-first for session data files — fetch fresh when possible, fall back to cache offline
  if (url.includes('/sessions/') || url.includes('sessions.json')) {
    e.respondWith(
      caches.open(CACHE).then(c =>
        fetch(e.request).then(r => { c.put(e.request, r.clone()); return r; }).catch(() => c.match(e.request))
      )
    );
    return;
  }

  // Network-first for app shell (HTML, manifest) — always get latest, fall back to cache offline
  if (url.endsWith('/') || url.endsWith('.html') || url.endsWith('.json')) {
    e.respondWith(
      caches.open(CACHE).then(c =>
        fetch(e.request).then(r => { c.put(e.request, r.clone()); return r; }).catch(() => c.match(e.request))
      )
    );
    return;
  }

  // Cache-first for CDN assets (Chart.js) and icons
  e.respondWith(
    caches.open(CACHE).then(c =>
      c.match(e.request).then(r => {
        if (r) return r;
        return fetch(e.request).then(nr => { c.put(e.request, nr.clone()); return nr; });
      })
    )
  );
});
