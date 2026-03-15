import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SidebarInset, SidebarProvider } from '@repo/ui/components';
import { AppSidebar } from '@/app/(protected)/_components/sidebar';
import { LOGIN_ROUTE } from '@/config/routes';
import { getSettings } from '@/lib/api/settings';
import { getSession } from '@/lib/auth';
import { ACTIVE_CURRENCY_COOKIE, ORIGINAL_CURRENCY } from '@/lib/stores/currency-store';

const FALLBACK_PRIMARY = process.env.NEXT_PUBLIC_FALLBACK_PRIMARY_CURRENCY ?? 'ARS';
const FALLBACK_SECONDARY = process.env.NEXT_PUBLIC_FALLBACK_SECONDARY_CURRENCY ?? 'USD';

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();

  if (!session?.user || (session.user as { error?: string }).error) {
    redirect(LOGIN_ROUTE);
  }

  const settings = await getSettings().catch(() => null);
  const cookieStore = await cookies();

  const primary = settings?.primary_currency ?? FALLBACK_PRIMARY;
  const secondary = settings?.secondary_currency ?? FALLBACK_SECONDARY;
  const displayCurrencies = secondary
    ? [primary, secondary, ORIGINAL_CURRENCY]
    : [primary, ORIGINAL_CURRENCY];

  const savedCurrency = cookieStore.get(ACTIVE_CURRENCY_COOKIE)?.value ?? null;
  const activeCurrency =
    savedCurrency && displayCurrencies.includes(savedCurrency) ? savedCurrency : primary;

  return (
    <SidebarProvider>
      <AppSidebar displayCurrencies={displayCurrencies} activeCurrency={activeCurrency} />
      <SidebarInset>
        <main className="flex flex-col min-h-full">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
