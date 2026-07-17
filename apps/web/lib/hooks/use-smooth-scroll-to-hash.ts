'use client';

import { useCallback } from 'react';
import { useReducedMotion } from 'motion/react';

/*
 * Returns a delegated click handler for in-page hash links (e.g. a table of contents). Put it as
 * `onClick` on the links' common container: a click on any `<a href="#id">` inside smoothly scrolls
 * to that element instead of jumping. Honors reduced motion (an explicit instant jump) and updates
 * the URL hash via replaceState (so the back button isn't polluted with every jump); the target's
 * own `scroll-mt-*` keeps it clear of a sticky header. After scrolling it moves focus to the target
 * (as native hash navigation would) so keyboard/screen-reader users continue from the section they
 * jumped to, not the link. Use plain `<a href="#id">` for the links — a Next <Link> handles the
 * click itself and would fight the delegation.
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
      // 'instant' (not 'auto') guarantees the reduced-motion jump regardless of any global
      // scroll-behavior; keep the current router state so replaceState only swaps the hash.
      target.scrollIntoView({ behavior: reduceMotion ? 'instant' : 'smooth', block: 'start' });
      history.replaceState(history.state, '', hash);
      // Move focus to the target without re-scrolling, so it isn't stranded on the off-screen link.
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    },
    [reduceMotion],
  );
}
