'use client';

import { Filter } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { accountLedgerPath } from '@/config/routes';
import { MOVEMENT_KINDS, type MovementKind } from '@/lib/constants/accounts';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';

interface AccountLedgerToolbarProps {
  accountId: number;
  // The kind the PAGE resolved, not the raw param: an unrecognized `?kind=` renders the whole
  // ledger, so re-reading the URL here would label the chip with a filter that isn't applied (and
  // with an unmapped value, print the raw translation key).
  kind?: MovementKind;
}

// The ledger's only filter. There is no search box: the rows are movements rather than named
// entities, and the three columns worth searching (category, counterparty, notes) each belong to a
// different subset of kinds — filtering by kind is the question this surface actually gets asked.
export function AccountLedgerToolbar({ accountId, kind }: AccountLedgerToolbarProps) {
  const t = useTranslations('accounts.ledger');
  // A kind change resets pagination — page 4 of "all" is rarely a page of "settlements".
  const { navigate } = useSearchParamsNavigation(accountLedgerPath(accountId), { resetPage: true });

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <FilterCombobox
        items={MOVEMENT_KINDS}
        value={kind ?? CATEGORY_ALL}
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
