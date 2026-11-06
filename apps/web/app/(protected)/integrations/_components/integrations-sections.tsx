import { IntegrationsApiKeys } from '@/app/(protected)/integrations/_components/integrations-api-keys';
import { IntegrationsShortcut } from '@/app/(protected)/integrations/_components/integrations-shortcut';
import type { ApiKey } from '@/lib/api/api-keys';
import type { SettingsData } from '@/lib/api/settings';
import { FALLBACK_PRIMARY_CURRENCY, FALLBACK_SECONDARY_CURRENCY } from '@/lib/constants/currency';

interface IntegrationsSectionsProps {
  apiKeys: ApiKey[];
  settings: SettingsData | null;
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

// The integrations page's sections under its header — rendered by the page, and as its placeholder by
// its loading state.
export function IntegrationsSections({ apiKeys, settings }: IntegrationsSectionsProps) {
  return (
    <>
      <IntegrationsApiKeys initialKeys={apiKeys} />
      <IntegrationsShortcut
        initialCurrencies={settings?.shortcutCurrencies ?? null}
        defaultCurrencies={buildDefaultCurrencies(settings)}
      />
    </>
  );
}
