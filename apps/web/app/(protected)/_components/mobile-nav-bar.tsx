import { getTranslations } from 'next-intl/server';

import { SidebarTrigger } from '@repo/ui/components';
import { Brand } from '@/components/brand';

/*
 * The small-screen navigation bar, and the only way into the nav below `md`.
 *
 * Under `MOBILE_BREAKPOINT` (768px) the sidebar renders as a Radix Sheet, and a closed Sheet is
 * UNMOUNTED — so the whole nav is absent from the DOM until something calls `toggleSidebar()`.
 * `SidebarTrigger` has always existed for exactly this and was simply never rendered, which left
 * every route below 768px with no way to reach any other route, quick-add, the currency switcher,
 * settings, or sign-out.
 *
 * Hidden from `md` up, where the sidebar is permanently visible and a second trigger would be noise.
 * The breakpoint is the SAME number on both sides: Tailwind's `md` is 768px and `useIsMobile()`
 * matches `max-width: 767px`, so the bar appears exactly where the Sheet takes over, with no width
 * at which both or neither is shown.
 *
 * A plain `div` rather than a `header`: the Sheet already carries the navigation landmark, so a
 * second landmark here would only add a region a screen reader has to step through on the way to it.
 */
export async function MobileNavBar() {
  const t = await getTranslations('sidebar');

  return (
    <div className="flex md:hidden items-center shrink-0 px-4 py-3 gap-x-2 bg-background border-b border-sidebar-border">
      <SidebarTrigger />
      <Brand name={t('brand')} size="md" />
    </div>
  );
}
