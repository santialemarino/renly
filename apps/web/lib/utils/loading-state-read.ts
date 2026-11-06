import { LOADING_STATE_READ_TIMEOUT_MS } from '@/lib/constants/animations';

/*
 * A read a loading state draws from, bounded: the read's value, or `fallback` when it fails or takes
 * longer than `timeoutMs` — so a slow or hanging API can delay the loading state by at most that,
 * never hold it back for good. The read itself is not cancelled: the page shares it (request cache).
 */
export async function readForLoadingState<T>(
  read: Promise<T>,
  fallback: T,
  timeoutMs: number = LOADING_STATE_READ_TIMEOUT_MS,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<T>((resolve) => {
    timer = setTimeout(() => resolve(fallback), timeoutMs);
  });
  try {
    return await Promise.race([read.catch(() => fallback), timeout]);
  } finally {
    clearTimeout(timer);
  }
}
