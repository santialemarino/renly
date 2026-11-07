/*
 * Starts a read now so it runs alongside the ones before it, for a page that must await something else
 * first — the record it is about, whose absence is a `notFound()` that has to win over any error the
 * other reads would raise for a record that does not exist. The read's rejection is still thrown where
 * it is awaited; it is only kept from being reported as unhandled while the page is awaiting the first.
 */
export function startRead<T>(read: Promise<T>): Promise<T> {
  read.catch(() => undefined);
  return read;
}
