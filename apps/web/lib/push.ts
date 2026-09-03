/*
 * The browser half of web push: registering the service worker, asking for permission, and turning a
 * PushSubscription into the three values the API stores.
 *
 * Separated from the component that calls it because none of it is React — it is four browser APIs
 * (ServiceWorkerContainer, Notification, PushManager, atob) with a fair amount of feature detection
 * around them, and a component holding that is a component nothing can read.
 *
 * Nothing here talks to Renly's API. The component owns that, so this module can be reasoned about as
 * "what did the browser say" and nothing else.
 */

/** The service worker's path. Static, at the origin root, so its scope covers the whole app. */
const SERVICE_WORKER_PATH = '/sw.js';

/*
 * Thrown when the person has refused notifications for this site.
 *
 * Its own error type because it is the one failure a retry cannot fix: a browser that has been told
 * "no" will not ask again, so the only way out is the browser's own site settings, and the surface has
 * to say that instead of offering the button once more.
 */
export class PushPermissionDeniedError extends Error {
  constructor() {
    super('Notifications are blocked for this site.');
    this.name = 'PushPermissionDeniedError';
  }
}

/** What the API stores about one browser: where to send, and the two keys the payload is sealed with. */
export interface PushSubscriptionKeys {
  endpoint: string;
  p256dh: string;
  auth: string;
}

/*
 * Whether this browser can receive web push at all.
 *
 * All three checks are needed and none is redundant: Safari had Notification without PushManager for
 * years, and every iOS browser has ServiceWorker but no PushManager until the app is added to the home
 * screen — which is a real state a real person can be in, not a theoretical one.
 */
export function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/*
 * The base64url applicationServerKey as the byte array `subscribe` wants.
 *
 * The Push API takes a Uint8Array here and rejects a string, and the key travels as base64url (no
 * padding, `-` and `_` for `+` and `/`) — so both halves of this conversion are load-bearing and a
 * plain atob would fail on roughly half of all keys.
 */
function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
  const binary = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  // Backed by an explicit ArrayBuffer rather than by `Uint8Array.from`, whose result is typed over
  // ArrayBufferLike — which includes SharedArrayBuffer and so is not the BufferSource `subscribe`
  // accepts.
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** One of the subscription's keys as base64url, which is how the API stores and re-reads it. */
function encodeKey(subscription: PushSubscription, name: 'p256dh' | 'auth'): string {
  const raw = subscription.getKey(name);
  if (!raw) throw new Error(`The push subscription is missing its ${name} key.`);
  const binary = String.fromCharCode(...new Uint8Array(raw));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/*
 * The registered service worker, registering it if this is the first time.
 *
 * `navigator.serviceWorker.ready` on its own is not enough: it never resolves when nothing has been
 * registered yet, so a first visit would hang forever on a promise with no error.
 */
async function serviceWorker(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_PATH);
  if (existing) return existing;
  await navigator.serviceWorker.register(SERVICE_WORKER_PATH);
  return navigator.serviceWorker.ready;
}

/*
 * This browser's current subscription endpoint, or null when it has none.
 *
 * Read from the BROWSER rather than from the account, because "this browser is subscribed" and "this
 * account has two browsers subscribed" are different questions and only the first one decides which
 * button to show. Returns null rather than throwing when push is unsupported, so a caller can ask
 * unconditionally.
 */
export async function currentPushEndpoint(): Promise<string | null> {
  if (!isPushSupported()) return null;
  try {
    const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_PATH);
    const subscription = await registration?.pushManager.getSubscription();
    return subscription?.endpoint ?? null;
  } catch {
    return null;
  }
}

/*
 * Asks for permission, subscribes, and returns the three values the API needs.
 *
 * `userVisibleOnly: true` is mandatory — Chrome refuses to subscribe without it, and it is also an
 * honest declaration: every push Renly sends shows a notification, none of them is a silent
 * background wake-up.
 *
 * An EXISTING subscription is reused rather than replaced. Re-subscribing would mint a new endpoint
 * and orphan the old row, so the account would accumulate a dead subscription per visit.
 */
export async function enablePush(applicationServerKey: string): Promise<PushSubscriptionKeys> {
  if (!isPushSupported()) throw new Error('This browser does not support web push.');
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new PushPermissionDeniedError();

  const registration = await serviceWorker();
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(applicationServerKey),
    }));

  return {
    endpoint: subscription.endpoint,
    p256dh: encodeKey(subscription, 'p256dh'),
    auth: encodeKey(subscription, 'auth'),
  };
}

/*
 * Unsubscribes this browser. The service worker registration is deliberately LEFT in place: it costs
 * nothing, and unregistering it would mean a fresh install (and a fresh permission prompt) the next
 * time somebody turns push back on.
 */
export async function disablePush(): Promise<void> {
  if (!isPushSupported()) return;
  const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_PATH);
  const subscription = await registration?.pushManager.getSubscription();
  await subscription?.unsubscribe();
}
