'use client';

import { useLayoutEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';

import {
  ANIMATION_DEFAULT,
  PAGE_SKELETON_DELAY_MS,
  PAGE_SKELETON_MIN_VISIBLE_MS,
} from '@/lib/constants/animations';

// A route's loading state (`PageSkeletonView`).
const SKELETON = '[data-page-skeleton]';
const FADE_MS = ANIMATION_DEFAULT * 1000;

interface PageEntranceProps {
  children: React.ReactNode;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/*
 * When a loading state's entrance began (its delay included), read off its CSS animation. One whose
 * animation has already finished has been up for longer than any hold, so it reads as long ago.
 */
function entranceStart(skeleton: HTMLElement): number {
  const animation = skeleton.getAnimations()[0];
  const now = performance.now();
  return animation
    ? now - Number(animation.currentTime ?? 0)
    : now - PAGE_SKELETON_DELAY_MS - PAGE_SKELETON_MIN_VISIBLE_MS;
}

/*
 * Every protected page's entrance, rendered by the protected template. The CSS (`.page-entrance` in
 * `globals.css`) does the main part with no script, so it runs on the server-rendered HTML:
 *
 * - the page fades in once, as a whole, when it mounts or when its loading state gives way to it;
 * - the loading state is invisible for `PAGE_SKELETON_DELAY_MS` and only then fades in, so a fast
 *   load shows nothing in between and a slow one shows the skeleton rather than a frozen screen.
 *
 * Two things CSS cannot do are done here, once hydrated:
 *
 * - **A minimum once shown.** Suspense removes a loading state in one commit, so a load landing just
 *   past the delay would flash it. When a loading state goes after being visible for less than
 *   `PAGE_SKELETON_MIN_VISIBLE_MS`, an inert copy of it stays over the page for the rest of that time
 *   and then crossfades into it; the page underneath is rendered and hydrated, only transparent. A
 *   loading state that never became visible holds nothing back.
 * - **A fade between pages of one section.** Next keeps the template when only a deeper segment
 *   changes (`/accounts` → `/accounts/12`), so a page served from the router cache would swap in
 *   with no fade; a pathname change with no loading state on screen fades the page in.
 *
 * Reduced motion: no fades — the copy and the page swap at once when the minimum is up.
 */
export function PageEntrance({ children }: PageEntranceProps) {
  const pathname = usePathname();

  const contentRef = useRef<HTMLDivElement>(null);
  const holdRef = useRef<HTMLDivElement>(null);
  const shownPathname = useRef(pathname);

  useLayoutEffect(() => {
    const content = contentRef.current;
    const hold = holdRef.current;
    if (!content || !hold) return;

    let skeleton: HTMLElement | null = null;
    let startedAt = 0;

    const release = (gone: HTMLElement, visibleFor: number) => {
      if (visibleFor <= 0 || visibleFor >= PAGE_SKELETON_MIN_VISIBLE_MS) return;
      const remaining = PAGE_SKELETON_MIN_VISIBLE_MS - visibleFor;
      const duration = prefersReducedMotion() ? 0 : FADE_MS;

      // The copy carries no ids, test ids or entrance rule of its own: it is a picture of the state.
      const copy = gone.cloneNode(true) as HTMLElement;
      copy.removeAttribute('data-page-skeleton');
      for (const element of [copy, ...copy.querySelectorAll<HTMLElement>('[id], [data-testid]')]) {
        element.removeAttribute('id');
        element.removeAttribute('data-testid');
      }
      copy.setAttribute('data-testid', 'page-skeleton-hold');
      hold.replaceChildren(copy);

      // Carries on the loading state's own fade-in from where it was.
      if (duration > 0 && visibleFor < FADE_MS) {
        copy.animate([{ opacity: 0 }, { opacity: 1 }], {
          duration: FADE_MS,
          delay: -visibleFor,
          easing: 'ease-out',
        });
      }
      const out = hold.animate([{ opacity: 1 }, { opacity: 0 }], {
        delay: remaining,
        duration,
        fill: 'forwards',
      });
      content.animate([{ opacity: 0 }, { opacity: 1 }], {
        delay: remaining,
        duration,
        easing: 'ease-out',
        fill: 'backwards',
      });
      out.finished
        .then(() => {
          hold.replaceChildren();
          out.cancel();
        })
        .catch(() => undefined);
    };

    const track = () => {
      if (skeleton && !content.contains(skeleton)) {
        release(skeleton, performance.now() - startedAt - PAGE_SKELETON_DELAY_MS);
        skeleton = null;
      }
      if (!skeleton) {
        const found = content.querySelector<HTMLElement>(SKELETON);
        if (found) {
          skeleton = found;
          startedAt = entranceStart(found);
        }
      }
    };

    // Mutation callbacks run before the next paint, so the copy is in place before the swap shows.
    const observer = new MutationObserver(track);
    observer.observe(content, { childList: true, subtree: true });
    track();
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (pathname === shownPathname.current) return;
    shownPathname.current = pathname;
    const content = contentRef.current;
    // A loading state on screen means the CSS fades the page in when it arrives.
    if (!content || content.querySelector(SKELETON) || prefersReducedMotion()) return;
    content.animate([{ opacity: 0 }, { opacity: 1 }], { duration: FADE_MS, easing: 'ease-out' });
  }, [pathname]);

  return (
    <div
      className="relative flex flex-col flex-1 min-w-0"
      style={
        {
          '--page-entrance-duration': `${ANIMATION_DEFAULT}s`,
          '--page-skeleton-delay': `${PAGE_SKELETON_DELAY_MS}ms`,
        } as React.CSSProperties
      }
    >
      <div ref={contentRef} className="page-entrance flex flex-col flex-1 min-w-0">
        {children}
      </div>
      <div
        ref={holdRef}
        aria-hidden="true"
        className="absolute inset-x-0 top-0 pointer-events-none"
        data-testid="page-entrance-hold"
        inert
      />
    </div>
  );
}
