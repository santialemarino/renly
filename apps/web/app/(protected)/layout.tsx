import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SidebarInset, SidebarProvider } from '@repo/ui/components';
import { LanguageAutoSync } from '@/app/(protected)/_components/language-auto-sync';
import { AppSidebar } from '@/app/(protected)/_components/sidebar';
import { TimezoneAutoSync } from '@/app/(protected)/_components/timezone-auto-sync';
import { LOGIN_ROUTE } from '@/config/routes';
import { getSettings } from '@/lib/api/settings';
import { getSession } from '@/lib/auth';
import { FALLBACK_PRIMARY_CURRENCY, FALLBACK_SECONDARY_CURRENCY } from '@/lib/constants/currency';
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

  const settings = await getSettings().catch(() => null);
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

  return (
    <SidebarProvider>
      {settings && (
        <>
          <TimezoneAutoSync storedTimezone={settings.timezone} storedMode={settings.timezoneMode} />
          <LanguageAutoSync storedLanguage={settings.language} storedMode={settings.languageMode} />
        </>
      )}
      <AppSidebar
        displayCurrencies={displayCurrencies}
        activeCurrency={activeCurrency}
        currencyCollapsed={currencyCollapsed}
      />
      <SidebarInset className="min-w-0">
        <main className="flex-1 flex flex-col min-w-0 overflow-x-hidden overflow-y-auto">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
