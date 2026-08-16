import { getTranslations } from 'next-intl/server';

import { Badge } from '@repo/ui/components';
import type { Account } from '@/lib/api/accounts';
import { getFormatters } from '@/lib/i18n/formatters-server';

interface AccountLedgerHeaderProps {
  account: Account;
}

// The account's identity and standing above its ledger: what it is, what it holds now, and the two
// dates that bound the movements below — `openingDate`, before which nothing is listed because
// `openingBalance` already contains it, and the last true-up.
export async function AccountLedgerHeader({ account }: AccountLedgerHeaderProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('accounts');

  const stats = [
    { label: t('ledger.stats.balance'), value: fmt.amount(account.balance, account.currency) },
    { label: t('ledger.stats.opened'), value: fmt.date(account.openingDate) },
    {
      label: t('ledger.stats.lastReconciled'),
      value: account.lastReconciledDate
        ? fmt.date(account.lastReconciledDate)
        : t('table.neverReconciled'),
    },
  ];

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-heading-2 text-foreground">{account.name}</h1>
        {!account.isActive && <Badge variant="secondary">{t('ledger.archived')}</Badge>}
      </div>
      <h2 className="text-paragraph text-muted-foreground">
        {t('ledger.subtitle', { type: t(`types.${account.type}`), currency: account.currency })}
      </h2>

      <dl className="grid grid-cols-1 sm:grid-cols-3 p-4 gap-x-6 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-y-1">
            <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
