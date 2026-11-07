'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

import { AUTOSAVE_COALESCE_MS } from '@/lib/constants/autosave';

/*
 * A refusal the server answered with (a 409's `conflictDetail`), thrown by a `write` so the hook treats
 * it as a failure and the caller can still show the server's own words.
 */
export class AutosaveRefusal extends Error {}

// The message a failed save shows: the server's refusal when it gave one, the caller's own otherwise.
export function autosaveErrorMessage(error: unknown, fallback: string): string {
  return error instanceof AutosaveRefusal && error.message ? error.message : fallback;
}

interface AutosaveTogglesOptions<V> {
  // The last value the server confirmed for a control, read from the caller's own state.
  confirmed: (key: string) => V;
  // Writes one control's value. Resolves once the server accepted it — the caller records the answer
  // in its confirmed state before resolving — and rejects on any failure.
  write: (key: string, value: V) => Promise<void>;
  // Called once per failed save, after the control is back on its confirmed value.
  onError: (key: string, error: unknown) => void;
  // Called when a save lands and no control has a write waiting or in flight.
  onSettled?: () => void;
  equals?: (a: V, b: V) => boolean;
  coalesceMs?: number;
}

interface Entry<V> {
  // What the person last asked for.
  intended: V;
  // What the server last accepted for this control during this burst.
  confirmed: V;
  timer: ReturnType<typeof setTimeout> | null;
  inFlight: boolean;
}

/*
 * Toggles that save on their own — a switch whose click IS the save — made optimistic: the control
 * shows the new value the instant it is clicked and stays interactive while the write goes out behind
 * it.
 *
 * Per control (a string key), three rules:
 *
 * - A burst coalesces. Each click restarts a short wait (`AUTOSAVE_COALESCE_MS`), and only the value
 *   the control holds when the clicks stop is written — once, and not at all when the burst ends where
 *   it began.
 * - Writes are serial. A click while the control's write is in flight waits for it to settle, then
 *   writes the newest value, so two answers for one control can never arrive out of order and the last
 *   intent is always what the server ends with.
 * - A failure rolls back. The control returns to its last confirmed value (any newer intent is
 *   dropped with it) and `onError` reports it; other controls' saves carry on untouched.
 *
 * The optimistic value is held until the caller's own confirmed state shows it, so the control never
 * flickers back between a write landing and the caller's state catching up.
 */
export function useAutosaveToggles<V>(options: AutosaveTogglesOptions<V>) {
  const latest = useRef(options);
  useLayoutEffect(() => {
    latest.current = options;
  });
  const entries = useRef(new Map<string, Entry<V>>());
  const [overrides, setOverrides] = useState<ReadonlyMap<string, V>>(() => new Map());

  const equals = useCallback((a: V, b: V) => (latest.current.equals ?? Object.is)(a, b), []);

  const setOverride = useCallback((key: string, value: V | undefined) => {
    setOverrides((current) => {
      const next = new Map(current);
      if (value === undefined) next.delete(key);
      else next.set(key, value);
      return next;
    });
  }, []);

  const flush = useCallback(
    (key: string) => {
      const entry = entries.current.get(key);
      if (!entry || entry.inFlight || entry.timer !== null) return;
      const value = entry.intended;
      // Nothing to write: the burst ended where the server already is.
      if (equals(value, entry.confirmed)) {
        entries.current.delete(key);
        setOverride(key, undefined);
        return;
      }
      entry.inFlight = true;
      latest.current.write(key, value).then(
        () => {
          entry.inFlight = false;
          entry.confirmed = value;
          // A newer intent is still waiting out its burst, or has already: write it next.
          if (entry.timer !== null) return;
          if (!equals(entry.intended, value)) {
            flush(key);
            return;
          }
          // Settled. The override stays until the caller's confirmed state shows the value.
          entries.current.delete(key);
          if (entries.current.size === 0) latest.current.onSettled?.();
        },
        (error: unknown) => {
          if (entry.timer !== null) clearTimeout(entry.timer);
          entries.current.delete(key);
          setOverride(key, undefined);
          latest.current.onError(key, error);
        },
      );
    },
    [equals, setOverride],
  );

  const set = useCallback(
    (key: string, value: V) => {
      let entry = entries.current.get(key);
      if (!entry) {
        const confirmed = latest.current.confirmed(key);
        entry = { intended: value, confirmed, timer: null, inFlight: false };
        entries.current.set(key, entry);
      }
      const current = entry;
      current.intended = value;
      setOverride(key, value);
      if (current.timer !== null) clearTimeout(current.timer);
      current.timer = setTimeout(() => {
        current.timer = null;
        flush(key);
      }, latest.current.coalesceMs ?? AUTOSAVE_COALESCE_MS);
    },
    [flush, setOverride],
  );

  // This render's confirmed state, not the ref's: the ref is updated only after the render commits.
  const { confirmed } = options;

  // Drops each settled override once the caller's confirmed state has caught up with it. `confirmed`
  // is a new function on every render, so this runs after each one; it sets state only when an
  // override is actually dropped.
  useEffect(() => {
    const caughtUp = [...overrides].filter(
      ([key, value]) => !entries.current.has(key) && equals(confirmed(key), value),
    );
    if (caughtUp.length === 0) return;
    setOverrides((current) => {
      const next = new Map(current);
      caughtUp.forEach(([key]) => next.delete(key));
      return next;
    });
  }, [overrides, equals, confirmed]);

  // A burst still waiting when the control goes (a click, then a navigation) is written at once
  // rather than lost. Nobody is left to show its outcome, so a failure is swallowed.
  useEffect(() => {
    const pending = entries.current;
    return () => {
      pending.forEach((entry, key) => {
        if (entry.timer === null) return;
        clearTimeout(entry.timer);
        if (!entry.inFlight && !equals(entry.intended, entry.confirmed)) {
          void latest.current.write(key, entry.intended).catch(() => undefined);
        }
      });
    };
  }, [equals]);

  const value = (key: string): V =>
    overrides.has(key) ? (overrides.get(key) as V) : confirmed(key);
  const isPending = (key: string) => overrides.has(key);

  return { value, set, isPending };
}
