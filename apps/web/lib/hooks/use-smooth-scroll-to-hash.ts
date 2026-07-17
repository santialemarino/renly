'use client';

import { useCallback } from 'react';
import { useReducedMotion } from 'motion/react';

/*
 * Returns a delegated click handler for in-page hash links (e.g. a table of contents). Put it as
 * `onClick` on the links' common container: a click on any `<a href="#id">` inside smoothly scrolls
 * to that element instead of jumping. Honors reduced motion (instant jump) and updates the URL hash
 * via replaceState (so the back button isn't polluted with every jump); the target's own
 * `scroll-mt-*` keeps it clear of a sticky header. Use plain `<a href="#id">` for the links — a Next
 * <Link> handles the click itself and would fight the delegation.
 */
export function useSmoothScrollToHash() {
  const reduceMotion = useReducedMotion();

  return useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      const anchor = (event.target as HTMLElement).closest('a[href^="#"]');
      const hash = anchor?.getAttribute('href');
      if (!hash) return;
      const target = document.getElementById(hash.slice(1));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
      history.replaceState(null, '', hash);
    },
    [reduceMotion],
  );
}
