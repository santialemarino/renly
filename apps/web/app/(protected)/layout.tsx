import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SidebarInset, SidebarProvider } from '@repo/ui/components';
import { LanguageAutoSync } from '@/app/(protected)/_components/language-auto-sync';
import { AppSidebar } from '@/app/(protected)/_components/sidebar';
import { TimezoneAutoSync } from '@/app/(protected)/_components/timezone-auto-sync';
import { SIDEBAR_EXPANDED_COOKIE } from '@/config/constants';
import { LOGIN_ROUTE } from '@/config/routes';
import { getSupportedCurrencies } from '@/lib/api/exchange-rates';
import { getNotifications } from '@/lib/api/notifications';
import { getOnboardingStatus } from '@/lib/api/onboarding';
import { getSettings } from '@/lib/api/settings';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession } from '@/lib/auth';
import { FALLBACK_PRIMARY_CURRENCY, FALLBACK_SECONDARY_CURRENCY } from '@/lib/constants/currency';
import { NOTIFICATION_POPOVER_SIZE } from '@/lib/constants/notifications';
import { hasNoCoreData } from '@/lib/onboarding';
import {
  ACTIVE_CURRENCY_COOKIE,
  CURRENCY_COLLAPSED_COOKIE,
  ORIGINAL_CURRENCY,
} from '@/lib/stores/currency-store';

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();

  if (!session?.user || (session.user as { error?: string }).error) {
    redirect(LOGIN_ROUTE);
  }

  // Signup mode gates the admin "Invite people" item in the sidebar (only relevant in invite mode).
  // supportedCurrencies feeds the currency switcher's "not convertible" warning from the same
  // backend registry the entry pickers use (single source of truth); undefined on fetch error
  // fails open (no spurious warning).
  // The bell's rows come from here rather than from a client fetch, so the unread state is correct on
  // every navigation with nothing polling. It fails soft to an empty bell: a feed that cannot load must
  // not take the whole app's shell down with it.
  const [settings, { mode: signupMode }, supportedCurrencies, notifications] = await Promise.all([
    getSettings().catch(() => null),
    getSignupContext(),
    getSupportedCurrencies().catch(() => undefined),
    getNotifications(NOTIFICATION_POPOVER_SIZE).catch(() => null),
  ]);
  const cookieStore = await cookies();

  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const secondary = settings?.secondaryCurrency ?? FALLBACK_SECONDARY_CURRENCY;
  const displayCurrencies = secondary
    ? [primary, secondary, ORIGINAL_CURRENCY]
    : [primary, ORIGINAL_CURRENCY];

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? null;
  const activeCurrency =
    savedCurrency && displayCurrencies.includes(savedCurrency) ? savedCurrency : primary;
  const currencyCollapsed = cookieStore.get(CURRENCY_COLLAPSED_COOKIE)?.value === 'true';

  /*
   * Progressive disclosure (UX-7): a confirmed first-run newcomer (settings loaded, onboarding not
   * done, no data yet) gets a reduced sidebar + a "Show more" toggle; anyone with data or who
   * finished onboarding sees every module. Fail closed on a settings-load error (full sidebar) so an
   * established user is never flashed the newcomer nav. The status probe runs only for that case.
   */
  const onboarded = settings?.onboardingCompleted === true;
  const sidebarExpanded = cookieStore.get(SIDEBAR_EXPANDED_COOKIE)?.value === 'true';
  let initialExpanded = true;
  let showDisclosureToggle = false;
  if (settings && !onboarded) {
    const status = await getOnboardingStatus().catch(() => null);
    if (hasNoCoreData(status)) {
      showDisclosureToggle = true;
      initialExpanded = sidebarExpanded;
    }
  }

  return (
    <SidebarProvider>
      {settings && (
        <>
          <TimezoneAutoSync storedTimezone={settings.timezone} storedMode={settings.timezoneMode} />
          <LanguageAutoSync storedLanguage={settings.language} storedMode={settings.languageMode} />
        </>
      )}
      <AppSidebar
        notifications={notifications?.items ?? []}
        unreadNotifications={notifications?.unread ?? 0}
        displayCurrencies={displayCurrencies}
        activeCurrency={activeCurrency}
        supportedCurrencies={supportedCurrencies}
        currencyCollapsed={currencyCollapsed}
        primaryCurrency={primary}
        preferredCurrencies={settings?.preferredCurrencies ?? undefined}
        timeZone={settings?.timezone ?? undefined}
        isAdmin={session.user.isAdmin}
        signupMode={signupMode}
        initialExpanded={initialExpanded}
        showDisclosureToggle={showDisclosureToggle}
      />
      <SidebarInset className="min-w-0">
        <main className="flex-1 flex flex-col min-w-0 overflow-x-hidden overflow-y-auto">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
