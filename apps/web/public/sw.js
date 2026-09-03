/*
 * Renly's service worker. It exists for one reason — a browser can only receive web push through one —
 * and it deliberately does nothing else.
 *
 * In particular it does NOT cache. An offline strategy for a finance app is a way to show somebody a
 * stale balance and let them act on it, which is the opposite of what the rest of this app is careful
 * about; and a caching worker that ships once is then permanently in the way of every deploy. The two
 * listeners below are the whole file.
 *
 * Served from /sw.js, which is a static file in `public/`, so its scope is the whole origin. The auth
 * proxy lets it through: /sw.js is not a known protected route, so the gate falls through to the real
 * static response rather than redirecting to login (a worker that 302'd to a login page would register
 * as an HTML document and silently never receive anything).
 *
 * The payload is what the API sealed and the push service delivered: { title, body, url }. The title is
 * the group and the body carries NO figures — a notification renders on a lock screen, so the amount
 * waits for the app.
 */

// A push arrived. Renders it, or falls back to the app's own name if the payload is unreadable — a
// silent push would be a notification the browser counts and the person never sees.
self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = {};
  }
  const title = payload.title || 'Renly';
  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      // Groups a repeat of the same thing rather than stacking it: the overdue-valuation reminder can
      // legitimately arrive again next period, and two identical lines help nobody.
      tag: payload.url || 'renly',
      renotify: false,
      data: { url: payload.url || '/' },
    }),
  );
});

/*
 * Clicking one opens what it is about. Focuses an already-open Renly tab and navigates it rather than
 * opening a second one — a finance app people keep open in a pinned tab should not accumulate copies
 * of itself — and only falls back to a new window when none is open.
 */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
          return client.navigate(target).then((navigated) => (navigated || client).focus());
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
