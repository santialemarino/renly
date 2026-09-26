import { getTranslations } from 'next-intl/server';

import { Badge } from '@repo/ui/components';
import { PageHeader } from '@/app/(protected)/_components/page-header';
import { MoneyFigure } from '@/components/money-figure';
import type { Account } from '@/lib/api/accounts';
import { getFormatters } from '@/lib/i18n/formatters-server';

interface AccountLedgerHeaderProps {
  account: Account;
}

// The account's identity and standing above its ledger: what it is, what it holds now, and the two
// anchors the movements below are bounded by — the opening balance and date, before which nothing is
// listed because `openingBalance` already contains it, and the last true-up. The opening balance is
// shown because it is where the running-balance column starts: without it the oldest row's balance
// appears to come from nowhere.
export async function AccountLedgerHeader({ account }: AccountLedgerHeaderProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('accounts');

  const stats = [
    {
      label: t('ledger.stats.balance'),
      value: <MoneyFigure>{fmt.amount(account.balance, account.currency)}</MoneyFigure>,
    },
    {
      label: t('ledger.stats.opening'),
      value: (
        <>
          <MoneyFigure>{fmt.amount(account.openingBalance, account.currency)}</MoneyFigure>
          {` · ${fmt.date(account.openingDate)}`}
        </>
      ),
    },
    {
      label: t('ledger.stats.lastReconciled'),
      value: account.lastReconciledDate
        ? fmt.date(account.lastReconciledDate)
        : t('table.neverReconciled'),
    },
  ];

  return (
    <div className="flex flex-col gap-y-4">
      <PageHeader
        title={account.name}
        subtitle={t('ledger.subtitle', {
          type: t(`types.${account.type}`),
          currency: account.currency,
        })}
        trailing={!account.isActive && <Badge variant="secondary">{t('ledger.archived')}</Badge>}
      />

      {/*
       * Three columns only once the PANEL is wide enough for a long balance in each (`@2xl`), not
       * once the viewport is: at 768px the sidebar leaves the panel ~430px, and `sm:grid-cols-3` put a
       * twelve-digit balance in a 128px column, where it ran out over the next stat.
       */}
      <div className="@container">
        <dl className="grid grid-cols-1 @2xl:grid-cols-3 p-4 gap-x-6 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
          {stats.map((stat) => (
            <div key={stat.label} className="flex flex-col gap-y-1">
              <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
              <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
