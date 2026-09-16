// Deliberately does no caching of its own - the app already has its own
// offline story (see useOfflineSync/lib/offlineOutbox.ts, which queues
// mutations in localStorage and replays them on reconnect), so a caching
// service worker here would just add a second, competing source of
// staleness. This one exists purely to satisfy Chrome/Android's "add to
// home screen" installability requirement, which won't fire without a
// registered service worker that has a fetch handler - skipWaiting/clients.
// claim so a redeploy takes over immediately instead of waiting for every
// open tab to close first.
self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request))
})
