'use client';

import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  CreditCard,
  HandCoins,
  Scale,
  ScrollText,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { SignedAmountCell } from '@/components/signed-amount-cell';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { accountLedgerPath } from '@/config/routes';
import type { AccountMovement, AccountMovementList } from '@/lib/api/account-movements';
import type { MovementKind } from '@/lib/constants/accounts';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { useFormatters } from '@/lib/i18n/formatters';

const COLUMN_COUNT = 5;

// One icon per kind. Direction is carried by the amount's sign and colour, so these say WHAT the
// movement was rather than which way it went — except the two entry kinds, where the arrow is the
// clearest thing an icon can say. `Scale` is the same icon the Reconcile row action uses.
// The two shared kinds are deliberately not both `Users`: paying a person back is a hand of coins,
// while money crossing into or out of something jointly owned is about the people who own it.
const KIND_ICONS: Record<MovementKind, LucideIcon> = {
  income: ArrowDownLeft,
  expense: ArrowUpRight,
  transfer: ArrowLeftRight,
  settlement: CreditCard,
  group_settlement: HandCoins,
  ownership: Users,
  adjustment: Scale,
};

interface AccountLedgerTableProps {
  accountId: number;
  data: AccountMovementList;
  // True while a kind filter is applied: the running balance is withheld, so the column goes too.
  filtered: boolean;
  firstRun?: boolean;
}

// The account's movements, newest first. Read-only by design — the kinds are owned by several
// different surfaces with different edit affordances, and some of them (adjustments, any entry in a
// reserved category, and anything belonging to a group) are not editable from here at all. A footnote
// points at where each lives.
export function AccountLedgerTable({
  accountId,
  data,
  filtered,
  firstRun,
}: AccountLedgerTableProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts.ledger');
  // The direction phrasings and the cross-currency sub-line describe the same transfer rows the
  // transfers sub-table renders, so they stay in one namespace rather than being restated here.
  const tTransfers = useTranslations('accounts.transfers');
  const tCommon = useTranslations('common');
  const { navigate, isPending } = useSearchParamsNavigation(accountLedgerPath(accountId));

  const { items, total, page, pageSize, currency } = data;
  const totalPages = Math.ceil(total / pageSize);
  const showBalance = !filtered;

  /*
   * The row's headline: what happened, naming the other side when there is one. The counterparty is
   * resolved server-side for exactly this — a row has to say what it was even when the client's own
   * lists fail to load, or when the other side has since been archived.
   *
   * Direction comes from the sign, which reads correctly here because this page only ever shows a
   * PRIVATE account (the API's own lookup is the owner-scoped one). Money leaving it for a pot is a
   * contribution; money arriving from one is a withdrawal.
   */
  function describe(movement: AccountMovement) {
    const other = movement.counterparty ?? '—';
    const outgoing = Number(movement.amount) < 0;
    if (movement.kind === 'settlement') {
      return t('rows.settlement', { card: other });
    }
    if (movement.kind === 'transfer') {
      return tTransfers(outgoing ? 'table.sentTo' : 'table.receivedFrom', { account: other });
    }
    if (movement.source === 'shared_expense') {
      return t('rows.sharedExpense', { group: other });
    }
    if (movement.kind === 'group_settlement') {
      return t(outgoing ? 'rows.settleUpPaid' : 'rows.settleUpReceived', { person: other });
    }
    if (movement.kind === 'ownership') {
      // Named from the POT's side, which is where the words come from: money leaving this account
      // is a contribution INTO it. Keying them 'in'/'out' would invert against `outgoing` here.
      return t(outgoing ? 'rows.ownershipContribution' : 'rows.ownershipWithdrawal', {
        pot: other,
      });
    }
    return t(`kinds.${movement.kind}`);
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('table.date')}</TableHead>
              <TableHead>{t('table.movement')}</TableHead>
              <TableHead>{t('table.notes')}</TableHead>
              <TableHead className="text-right">{t('table.amountIn', { currency })}</TableHead>
              {showBalance && (
                <TableHead className="text-right">{t('table.balanceIn', { currency })}</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableEmptyRow
                colSpan={showBalance ? COLUMN_COUNT : COLUMN_COUNT - 1}
                firstRun={firstRun}
                icon={ScrollText}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={filtered ? t('table.emptyFiltered') : t('table.empty')}
              />
            ) : (
              items.map((movement) => {
                const Icon = KIND_ICONS[movement.kind];
                const outgoing = Number(movement.amount) < 0;
                // Both sides are shown only when they differ — that pair IS the record of the rate.
                const crossCurrency =
                  !!movement.counterpartyAmount &&
                  !!movement.counterpartyCurrency &&
                  movement.counterpartyCurrency !== currency;
                // Keyed on the SOURCE, not the kind: `adjustment` spans two tables with independent
                // id sequences, so two adjustments really can share (kind, sourceId).
                return (
                  <TableRow key={`${movement.source}-${movement.sourceId}`}>
                    <TableCell className="text-paragraph-sm-medium">
                      {fmt.date(movement.date)}
                    </TableCell>
                    <TableCell>
                      <span className="flex items-center gap-x-1.5 text-paragraph-sm">
                        <Icon className="size-4 shrink-0 text-muted-foreground" />
                        {describe(movement)}
                      </span>
                      {movement.category && (
                        <span className="block text-paragraph-xs text-muted-foreground">
                          {tCommon(`categories.${movement.category}`)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-48 truncate text-paragraph-sm text-muted-foreground">
                      {movement.notes ?? '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <SignedAmountCell
                        amount={movement.amount.replace(/^-/, '')}
                        currency={currency}
                        outgoing={outgoing}
                        subLine={
                          crossCurrency &&
                          t('rows.crossCurrency', {
                            amount: `${fmt.amount(movement.counterpartyAmount ?? '0', movement.counterpartyCurrency ?? undefined)} ${movement.counterpartyCurrency}`,
                          })
                        }
                      />
                    </TableCell>
                    {showBalance && (
                      <TableCell className="text-right text-paragraph-sm tabular-nums">
                        {movement.balanceAfter !== null
                          ? fmt.amount(movement.balanceAfter, currency)
                          : '—'}
                      </TableCell>
                    )}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <TablePagination
        page={page}
        totalPages={totalPages}
        totalLabel={t('table.total', { total })}
        onPageChange={(next) => navigate({ page: next > 1 ? String(next) : null })}
      />

      {items.length > 0 && (
        <div className="flex flex-col gap-y-1 text-paragraph-xs text-muted-foreground">
          {/* Explains the column the filter takes away, so its absence doesn't read as a bug. */}
          {filtered && <p>{t('table.filteredNote')}</p>}
          <p>{t('table.readOnlyNote')}</p>
        </div>
      )}
    </div>
  );
}
