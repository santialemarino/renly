'use client';

import { useSearchParams } from 'next/navigation';
import { Filter } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { accountLedgerPath } from '@/config/routes';
import { MOVEMENT_KINDS, type MovementKind } from '@/lib/constants/accounts';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

interface AccountLedgerToolbarProps {
  accountId: number;
}

// The ledger's only filter. There is no search box: the rows are movements rather than named
// entities, and the three columns worth searching (category, counterparty, notes) each belong to a
// different subset of kinds — filtering by kind is the question this surface actually gets asked.
export function AccountLedgerToolbar({ accountId }: AccountLedgerToolbarProps) {
  const t = useTranslations('accounts.ledger');
  const searchParams = useSearchParams();
  // A kind change resets pagination — page 4 of "all" is rarely a page of "settlements".
  const { navigate } = useSearchParamsNavigation(accountLedgerPath(accountId), { resetPage: true });

  const kind = searchParams.get('kind') ?? CATEGORY_ALL;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <FilterCombobox
        items={MOVEMENT_KINDS}
        value={kind}
        onValueChange={(value) => navigate({ kind: value === CATEGORY_ALL ? null : value })}
        labelFor={(value) => t(`kinds.${value as MovementKind}`)}
        allLabel={t('filter.all')}
        icon={Filter}
        surface
        className="w-full sm:w-56"
      />
    </div>
  );
}
