'use client';

import * as React from 'react';

/*
 * Where focus goes when a modal overlay closes: back to whatever opened it.
 *
 * Radix already does this, but only through its own `Dialog.Trigger`: the content's close handler
 * calls `preventDefault()` on FocusScope's own "return to the previously focused element" and focuses
 * `context.triggerRef` instead — which is null unless a `Dialog.Trigger` rendered. Almost every overlay
 * here is CONTROLLED (a toolbar button, a row action, the quick-add and the nav hamburger all flip an
 * `open` prop), so the ref is null and focus fell to `<body>` on every close, twenty-odd tab stops
 * from where the reader was.
 *
 * So the content records its own opener and returns to it. Four cases decide the shape:
 *
 *   * The opener is recorded when the content ELEMENT mounts (the returned `ref`), once per opening —
 *     not in Radix's `onOpenAutoFocus`, which FocusScope skips entirely when focus is already inside
 *     the content. React applies `autoFocus` before that, so a dialog that focuses its own input (the
 *     type-to-confirm deletes) never got the event and closed to `<body>`. A fresh mount also resets
 *     the chain, so a later opening can never reuse an earlier opener.
 *   * The opener is the element that held focus, or — when focus is already inside the content (that
 *     `autoFocus`), or on `<body>` (a trigger that disables itself while it loads, as the quick-add
 *     does; Safari never focuses a clicked button at all) — the most recent element the reader
 *     focused or pressed OUTSIDE the content, skipping any that have left the document. That scan is
 *     what returns the phone quick-add to the hamburger: its trigger leaves with the nav sheet before
 *     the form mounts, so the next interaction still in the page is the hamburger itself.
 *   * The opener may be in the page when the overlay opens and GONE when it closes: a follow-up
 *     dialog that mounts while the form before it is still animating out, with focus on that form's
 *     button (the amount-mismatch prompt after an expense form's Save). So each overlay keeps a
 *     CHAIN — its opener, then the chain of the overlay that opener sat in — and closing focuses the
 *     first link still in the document: the prompt returns to whatever opened the form.
 *   * Focus that has already landed somewhere real is left alone. A swap mounts the incoming form
 *     while the outgoing one is still animating out, and the outgoing one's close fires later; pulling
 *     focus back to the page from under the new form would be the opposite of the fix.
 *
 * The close handler is composed over the caller's own, which runs first and may `preventDefault()` to
 * take over, exactly as with Radix's prop.
 */

// Radix renders every dialog and sheet content with this role.
const OVERLAY_SELECTOR = '[role="dialog"]';
// Elements a person can focus or press. `tabindex="-1"` is excluded: a region made focusable for a
// skip link or a scroll target is where focus lands, not something that opened anything.
const INTERACTIVE_SELECTOR =
  'a[href], button, input, select, textarea, summary, [role="button"], [tabindex]:not([tabindex="-1"])';
// How many recent interactions to remember — enough to see past an overlay's own autofocus.
const RECENT_LIMIT = 10;

// Each open overlay's chain, keyed by its content element, so an overlay opened from inside another
// can inherit the outer one's.
const returnChains = new WeakMap<Element, HTMLElement[]>();
// The last few elements focused or pressed, most recent last.
const recent: HTMLElement[] = [];

function rememberInteraction(event: Event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const interactive = target.closest(INTERACTIVE_SELECTOR);
  if (!(interactive instanceof HTMLElement)) return;
  const index = recent.indexOf(interactive);
  if (index !== -1) recent.splice(index, 1);
  recent.push(interactive);
  if (recent.length > RECENT_LIMIT) recent.shift();
}

/*
 * Installed at module load rather than in an effect: the opener is focused or pressed BEFORE any
 * overlay content mounts, and the one overlay loaded on demand (the quick-add's forms) has no module
 * at all until then. Capture phase, so nothing that stops propagation can hide an interaction.
 */
if (typeof document !== 'undefined') {
  document.addEventListener('focusin', rememberInteraction, true);
  document.addEventListener('pointerdown', rememberInteraction, true);
}

// What opened `content`: the focused element, or failing that the latest interaction outside it.
function openerOf(content: Element): HTMLElement | null {
  const active = document.activeElement;
  if (active instanceof HTMLElement && active !== document.body && !content.contains(active))
    return active;
  for (let index = recent.length - 1; index >= 0; index -= 1) {
    const element = recent[index];
    if (element && element.isConnected && !content.contains(element)) return element;
  }
  return null;
}

interface ReturnFocusOptions<T extends HTMLElement> {
  // The caller's own close handler, composed rather than replaced.
  onCloseAutoFocus?: (event: Event) => void;
  // The caller's own ref to the content, forwarded by the returned ref.
  ref?: React.Ref<T>;
}

export function useReturnFocus<T extends HTMLElement>({
  onCloseAutoFocus,
  ref: callerRef,
}: ReturnFocusOptions<T>) {
  const chain = React.useRef<HTMLElement[]>([]);
  const latestCallerRef = React.useRef(callerRef);
  latestCallerRef.current = callerRef;

  // Stable, so React calls it once per mount of the content element rather than on every render.
  // The content element the chain was recorded for.
  const recordedFor = React.useRef<T | null>(null);

  /*
   * Records once per MOUNT of the content element. React calls a ref again on renders where the
   * composed ref around it changes identity (Radix composes several), and re-recording then would
   * overwrite the opener with whatever is focused by that time — a button in a follow-up dialog, an
   * option in a portaled popover. So a call for the node already recorded is ignored; only a new
   * node (a new opening) records again.
   */
  const ref = React.useCallback((content: T | null) => {
    const forward = latestCallerRef.current;
    if (typeof forward === 'function') forward(content);
    else if (forward) forward.current = content;
    if (!content || content === recordedFor.current) return;
    recordedFor.current = content;
    const opener = openerOf(content);
    const outer = opener?.closest(OVERLAY_SELECTOR);
    chain.current = opener ? [opener, ...((outer && returnChains.get(outer)) ?? [])] : [];
    returnChains.set(content, chain.current);
  }, []);

  const handleCloseAutoFocus = React.useCallback(
    (event: Event) => {
      onCloseAutoFocus?.(event);
      if (event.defaultPrevented) return;
      // Nothing recorded (no opener could be found at all): Radix's own behaviour.
      if (chain.current.length === 0) return;
      event.preventDefault();
      const active = document.activeElement;
      if (active instanceof HTMLElement && active !== document.body && active.isConnected) return;
      // A link can be in the document and still refuse focus (disabled, hidden), so each is tried
      // and checked rather than trusted.
      chain.current.some((element) => {
        if (!element.isConnected) return false;
        element.focus();
        return document.activeElement === element;
      });
    },
    [onCloseAutoFocus],
  );

  return { ref, onCloseAutoFocus: handleCloseAutoFocus };
}
