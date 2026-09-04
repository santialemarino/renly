'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { DIALOG_EXIT_MS } from '@/lib/constants/animations';

/*
 * Swapping one entry form for another, with the two never on screen at once.
 *
 * Three surfaces do this: the expenses toolbar and the income toolbar swap between the private form
 * and a group's shared one, and the global quick-add swaps on that axis AND on the expense/income one.
 * Each held its own copy of the same close-then-reopen timer, which was three places that had to agree
 * about one handoff — so it is one hook.
 *
 * The wait is not cosmetic. Two dialogs mounted at once stack two Radix overlays and double the dim;
 * letting the first finish its exit is what makes a swap read as one form changing rather than two
 * dialogs fighting.
 *
 * The target carries the in-progress values rather than holding them in a second piece of state, which
 * is what lets a caller give each target its own prefill TYPE — the two lists' handovers are bound to
 * their own category enum, and a single loose slot could not be checked. It also means nothing about
 * the outgoing dialog changes while it is animating out.
 */
export function useDeferredDialogSwap<TTarget>(initialTarget: TTarget) {
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<TTarget>(initialTarget);
  // The pending half of a swap, so an unmount between the close and the reopen cannot leave a timer
  // waking up to open a dialog on a page that has gone.
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelPending = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => cancelPending, [cancelPending]);

  /*
   * Opens a form from scratch. Any pending swap is CANCELLED first: a timer scheduled a moment ago
   * would otherwise fire afterwards and replace the form the user just asked for with the one they had
   * left, seeded with nothing.
   */
  const start = useCallback(
    (next: TTarget) => {
      cancelPending();
      setTarget(next);
      setOpen(true);
    },
    [cancelPending],
  );

  // Closes what is on screen, then opens `next` with whatever it carries.
  const swapTo = useCallback(
    (next: TTarget) => {
      cancelPending();
      setOpen(false);
      timer.current = setTimeout(() => {
        timer.current = null;
        setTarget(next);
        setOpen(true);
      }, DIALOG_EXIT_MS);
    },
    [cancelPending],
  );

  return { open, setOpen, target, start, swapTo };
}
