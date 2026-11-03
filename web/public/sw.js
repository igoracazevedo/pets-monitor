// Pets Monitor: recebe os avisos enviados pelo programa de casa e os mostra no celular/computador.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let d = {}
  try {
    d = event.data ? event.data.json() : {}
  } catch {
    d = { title: 'Pets Monitor', body: event.data ? event.data.text() : '' }
  }
  event.waitUntil(
    self.registration.showNotification(d.title || 'Pets Monitor', {
      body: d.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      image: d.image || undefined,
      tag: d.tag || undefined,
      renotify: !!d.tag,
      data: { url: d.url || '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((lista) => {
      for (const c of lista) if ('focus' in c) return c.focus()
      return self.clients.openWindow((event.notification.data && event.notification.data.url) || '/')
    }),
  )
})
