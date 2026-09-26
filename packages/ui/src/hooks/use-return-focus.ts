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
 * So the content records its own opener and returns to it. Three cases decide the shape:
 *
 *   * The opener is what held focus when the content mounted, read in `onOpenAutoFocus` — dispatched
 *     before FocusScope moves focus inside, so `activeElement` is still the opener. When that is
 *     `<body>` (a trigger that disables itself while it loads, as the quick-add does, drops focus
 *     before the dialog exists; Safari never focuses a clicked button at all), the last element the
 *     reader focused or pressed stands in for it.
 *   * The opener may be GONE by the time the overlay closes: a swapped-in form (`useDeferredDialogSwap`)
 *     was opened from a control inside the form it replaced, which has since unmounted. So each
 *     overlay keeps a CHAIN — its opener, then the chain of the overlay that opener sat in — and
 *     closing focuses the first link still in the document. A swapped form therefore returns to the
 *     button that opened the first one.
 *   * Focus that has already landed somewhere real is left alone. A swap mounts the incoming form
 *     while the outgoing one is still animating out, and the outgoing one's close fires later; pulling
 *     focus back to the page from under the new form would be the opposite of the fix.
 *
 * Returns the two handlers composed over the caller's own, which run first and may `preventDefault()`
 * to take over, exactly as with Radix's props.
 */

// Radix renders every dialog and sheet content with this role.
const OVERLAY_SELECTOR = '[role="dialog"]';
// Elements a person can focus or press. `tabindex="-1"` is excluded: a region made focusable for a
// skip link or a scroll target is where focus lands, not something that opened anything.
const INTERACTIVE_SELECTOR =
  'a[href], button, input, select, textarea, summary, [role="button"], [tabindex]:not([tabindex="-1"])';

// Each open overlay's chain, keyed by its content element, so an overlay opened from inside another
// can inherit the outer one's.
const returnChains = new WeakMap<Element, HTMLElement[]>();
let lastInteracted: HTMLElement | null = null;

function rememberInteraction(event: Event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const interactive = target.closest(INTERACTIVE_SELECTOR);
  if (interactive instanceof HTMLElement) lastInteracted = interactive;
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

function openerOf(): HTMLElement | null {
  const active = document.activeElement;
  if (active instanceof HTMLElement && active !== document.body) return active;
  return lastInteracted?.isConnected ? lastInteracted : null;
}

interface ReturnFocusHandlers {
  onOpenAutoFocus?: (event: Event) => void;
  onCloseAutoFocus?: (event: Event) => void;
}

export function useReturnFocus({ onOpenAutoFocus, onCloseAutoFocus }: ReturnFocusHandlers) {
  const chain = React.useRef<HTMLElement[]>([]);

  const handleOpenAutoFocus = React.useCallback(
    (event: Event) => {
      const opener = openerOf();
      const outer = opener?.closest(OVERLAY_SELECTOR);
      chain.current = opener ? [opener, ...((outer && returnChains.get(outer)) ?? [])] : [];
      if (event.target instanceof Element) returnChains.set(event.target, chain.current);
      onOpenAutoFocus?.(event);
    },
    [onOpenAutoFocus],
  );

  const handleCloseAutoFocus = React.useCallback(
    (event: Event) => {
      onCloseAutoFocus?.(event);
      if (event.defaultPrevented) return;
      // Nothing recorded (the content mounted with focus already inside it): Radix's own behaviour.
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

  return { onOpenAutoFocus: handleOpenAutoFocus, onCloseAutoFocus: handleCloseAutoFocus };
}
