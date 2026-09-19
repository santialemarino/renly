import { getTranslations } from 'next-intl/server';

import { SidebarTrigger } from '@repo/ui/components';
import { Brand } from '@/components/brand';
import { ROUTES } from '@/config/routes';

/*
 * The small-screen top bar, and the only way into the navigation below `md`.
 *
 * Under that width the sidebar renders as a Radix Sheet, and a closed Sheet is UNMOUNTED — so the
 * whole nav is absent from the DOM until something calls `toggleSidebar()`. `SidebarTrigger` has
 * always existed for exactly this and was simply never rendered, which left every route below the
 * breakpoint with no way to reach any other route, quick-add, the currency switcher, settings, or
 * sign-out.
 *
 * `md:hidden` is safe to pair with the Sheet because `useIsMobile()` now reads the same `48rem` media
 * query Tailwind compiles `md:` to. That was NOT true before: the hook compared `window.innerWidth`
 * against 768 pixels, so any reader whose browser font size moved Tailwind's `md` away from 768px got
 * a band where the sidebar was hidden, this bar was shown, and the trigger was inert.
 *
 * `sticky` because this is the only route out of the page on a phone. Static, it scrolls off the top
 * of a 2600px dashboard on the first flick and the reader has to scroll all the way back to leave.
 */
export async function MobileNavBar() {
  const t = await getTranslations('sidebar');

  return (
    <header className="sticky top-0 z-10 flex md:hidden items-center shrink-0 px-4 py-3 gap-x-2 bg-background border-b border-sidebar-border">
      <SidebarTrigger />
      {/* The wordmark is the conventional "back to the start" target in a phone header, and it is the
          only always-present one here — every other destination lives behind the trigger. */}
      <Brand name={t('brand')} href={ROUTES.dashboard} size="md" />
    </header>
  );
}
