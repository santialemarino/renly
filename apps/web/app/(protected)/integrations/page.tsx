import { getTranslations } from 'next-intl/server';

import { PageHeader } from '@/app/(protected)/_components/page-header';
import { IntegrationsApiKeys } from '@/app/(protected)/integrations/_components/integrations-api-keys';
import { IntegrationsShortcut } from '@/app/(protected)/integrations/_components/integrations-shortcut';
import { getApiKeys } from '@/lib/api/api-keys';
import type { SettingsData } from '@/lib/api/settings';
import { getSettings } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY, FALLBACK_SECONDARY_CURRENCY } from '@/lib/constants/currency';
import { generatePageMetadata } from '@/lib/utils/page-metadata';

export async function generateMetadata() {
  return await generatePageMetadata('integrations');
}

// Builds a deduplicated default currency string from the user's primary and secondary currencies.
function buildDefaultCurrencies(settings: SettingsData | null): string | null {
  const primary = settings?.primaryCurrency ?? FALLBACK_PRIMARY_CURRENCY;
  const secondary = settings?.secondaryCurrency ?? FALLBACK_SECONDARY_CURRENCY;

  const seen = new Set<string>();
  const result: string[] = [];
  [primary, secondary].forEach((c) => {
    if (c && !seen.has(c)) {
      seen.add(c);
      result.push(c);
    }
  });
  return result.length > 0 ? result.join(', ') : null;
}

export default async function IntegrationsPage() {
  const t = await getTranslations('integrations');
  const [apiKeys, settings] = await Promise.all([
    getApiKeys().catch(() => []),
    getSettings().catch(() => null),
  ]);

  const defaultCurrencies = buildDefaultCurrencies(settings);

  return (
    <div className="flex flex-col flex-1 items-start p-8 gap-y-4">
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <IntegrationsApiKeys initialKeys={apiKeys} />
      <IntegrationsShortcut
        initialCurrencies={settings?.shortcutCurrencies ?? null}
        defaultCurrencies={defaultCurrencies}
      />
    </div>
  );
}
