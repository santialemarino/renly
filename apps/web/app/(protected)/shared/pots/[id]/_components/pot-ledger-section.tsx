'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, History, Trash2, Undo2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import type { SharedMutationResult } from '@/app/(protected)/shared/mutation-result';
import {
  confirmPotOwnershipEvent,
  deletePotOwnershipEvent,
  unconfirmPotOwnershipEvent,
} from '@/app/(protected)/shared/pot-actions';
import { isOutgoingEvent, ownershipEventAmount } from '@/app/(protected)/shared/pot-rules';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { EmptyState } from '@/components/empty-state';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import { SignedAmountCell } from '@/components/signed-amount-cell';
import type { Pot, PotOwnershipEvent } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface PotLedgerSectionProps {
  pot: Pot;
  events: PotOwnershipEvent[];
}

/*
 * Everything that has ever moved this pot's ownership, in replay order — oldest first, which is the
 * order the balances are derived in and therefore the only order the history reads correctly in.
 *
 * No unit count appears anywhere: percentages go in and percentages come out, with units only in the
 * middle (U2). Each row's figure is the money that actually moved, except a re-agreement, which moves
 * none — there the figure is what the transferred share was worth on the day.
 *
 * Deleting an entry is offered because balances are DERIVED: the series simply recomputes without it,
 * with no stored total to correct. That is the same property that makes back-dating safe here while
 * account reconciliation stays forward-only.
 *
 * A re-agreement additionally carries a CONFIRMATION, and the three flags that govern it — `canDelete`,
 * `canConfirm`, `canUnconfirm` — arrive resolved from the API and are rendered as given (see
 * `pot-rules.ts` for why none of them is mirrored here). Between them they encode the one rule on this
 * page that write access does not decide: a re-agreement's two named seats may always remove it while
 * it is unconfirmed, because write access is granted to a pot's creator and nobody else — so without
 * that a co-owner could be moved out of their own share, be told so by name, and have no way back.
 * Agreeing is what closes it again, for everybody.
 *
 * Only the CONFIRMED state is badged, and the unconfirmed one deliberately looks exactly as it did
 * before this existed. The entry counted from the moment it was recorded, so "awaiting confirmation"
 * beside it would read as "not applied yet" about units that have already moved — the same objection
 * that rejected a pending gate in the first place. Silence is the honest default; the positive fact is
 * what gets marked.
 */
export function PotLedgerSection({ pot, events }: PotLedgerSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [pendingDelete, setPendingDelete] = useState<PotOwnershipEvent | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pending, setPending] = useState(false);

  // The title and confirm label sit outside ConfirmDialog's description callback, so they read the
  // retained entity directly — which is also what keeps the copy stable through the close animation.
  const isBaseline = pendingDelete?.type === 'opening';

  /*
   * One handler for all three acts on a row. Each returns its refusal as data rather than throwing, so
   * an entry somebody deleted or confirmed while this page sat open explains itself instead of failing
   * silently — the state on screen is a snapshot, and these are the acts most likely to race.
   */
  async function run(
    action: () => Promise<SharedMutationResult>,
    successMessage: string,
    errorMessage: string = t('pots.ledger.actionError'),
  ) {
    setPending(true);
    try {
      const result = await action();
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(successMessage);
      router.refresh();
    } catch {
      toast.error(errorMessage);
    } finally {
      setPending(false);
    }
  }

  // The delete runs through the same handler, which is what keeps its refusal, its loading state and
  // its refresh identical to the two above. It closes the dialog whatever happened — `run` never
  // throws, so this is the `finally` the inline version used to need.
  async function onDelete() {
    if (!pendingDelete) return;
    await run(
      () => deletePotOwnershipEvent(pot.id, pendingDelete.id),
      t(isBaseline ? 'pots.ledger.deleteBaselineSuccess' : 'pots.ledger.deleteSuccess'),
      t('pots.ledger.deleteError'),
    );
    setDeleteOpen(false);
  }

  return (
    <div className="flex flex-col gap-y-4">
      <SectionHeader title={t('pots.ledger.title')} description={t('pots.ledger.description')} />

      {events.length === 0 ? (
        <EmptyState
          icon={History}
          title={t('pots.ledger.emptyTitle')}
          description={t('pots.ledger.emptyDescription')}
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">{t('pots.ledger.table.date')}</TableHead>
              <TableHead className="w-36">{t('pots.ledger.table.type')}</TableHead>
              <TableHead>{t('pots.ledger.table.who')}</TableHead>
              <TableHead className="w-44 text-right">{t('pots.ledger.table.amount')}</TableHead>
              <TableHead className="w-28 text-center">{t('pots.ledger.table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((event) => (
              <LedgerRow
                key={event.id}
                pot={pot}
                event={event}
                disabled={pending}
                onConfirm={() =>
                  run(
                    () => confirmPotOwnershipEvent(pot.id, event.id),
                    t('pots.ledger.confirmSuccess'),
                  )
                }
                onUnconfirm={() =>
                  run(
                    () => unconfirmPotOwnershipEvent(pot.id, event.id),
                    t('pots.ledger.unconfirmSuccess'),
                  )
                }
                onDelete={() => {
                  setPendingDelete(event);
                  setDeleteOpen(true);
                }}
              />
            ))}
          </TableBody>
        </Table>
      )}

      {/*
       * The entity is kept as state and never nulled on close, so the copy does not blank out while
       * the dialog animates away.
       */}
      {/*
       * Two whole strings rather than one with the event type interpolated in. The baseline is ONE act
       * written as one row per owner, so deleting any of its rows deletes all of them — and a dialog
       * that said "this entry" while removing three would be lying about what the button does. Whole
       * strings also keep Spanish out of the gendered-determiner trap a label-in-prose creates.
       */}
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        entity={pendingDelete}
        title={t(isBaseline ? 'pots.ledger.deleteBaselineTitle' : 'pots.ledger.deleteTitle')}
        description={(event) =>
          t(
            event.type === 'opening'
              ? 'pots.ledger.deleteBaselineDescription'
              : 'pots.ledger.deleteDescription',
          )
        }
        onConfirm={onDelete}
        loading={pending}
        loadingLabel={t('pots.ledger.deleteLoading')}
        confirmLabel={t(
          isBaseline ? 'pots.ledger.deleteBaselineConfirm' : 'pots.ledger.deleteConfirm',
        )}
        cancelLabel={t('form.cancel')}
      />
    </div>
  );
}

function LedgerRow({
  pot,
  event,
  disabled,
  onConfirm,
  onUnconfirm,
  onDelete,
}: {
  pot: Pot;
  event: PotOwnershipEvent;
  disabled: boolean;
  onConfirm: () => void;
  onUnconfirm: () => void;
  onDelete: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const figure = ownershipEventAmount(event, pot.baseCurrency);

  return (
    <TableRow>
      <TableCell className="text-paragraph-sm tabular-nums">{fmt.date(event.date)}</TableCell>
      <TableCell>
        <div className="flex flex-wrap items-center gap-x-1 gap-y-1">
          <Badge variant="secondary">{t(`pots.eventTypes.${event.type}`)}</Badge>
          {/* Only the agreed state is stated. An unconfirmed entry has already moved the units, so a
              second badge there would describe it as pending when nothing about it is. */}
          {event.confirmedAt !== null && (
            <Badge data-testid="ledger-agreed-badge">{t('pots.ledger.agreed')}</Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="text-paragraph-sm">
        {/* A re-agreement is the only event with two sides, so it is the only one that reads as an
            arrow between people; every other row is about one member. */}
        {event.counterpartyName
          ? `${event.memberName} → ${event.counterpartyName}`
          : event.memberName}
        {event.notes && (
          <span className="block text-paragraph-xs text-muted-foreground">{event.notes}</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {figure === null ? (
          <span className="text-paragraph-sm text-muted-foreground">—</span>
        ) : (
          <SignedAmountCell
            amount={figure.amount}
            currency={figure.currency}
            outgoing={isOutgoingEvent(event)}
            subLine={
              // Only when the two legs are denominated differently: the pot was credited a figure the
              // person never transferred, and both are true at once.
              event.amountCurrency && event.baseAmount ? (
                <span>
                  {t('pots.ledger.credited', {
                    amount: fmt.amount(event.baseAmount, pot.baseCurrency),
                    currency: pot.baseCurrency,
                  })}
                </span>
              ) : undefined
            }
          />
        )}
      </TableCell>
      <TableCell className="text-center">
        <div className="flex items-center justify-center gap-x-1">
          {event.canConfirm && (
            <RowActionButton
              icon={Check}
              tooltip={t('pots.ledger.actions.confirm')}
              ariaLabel="Agree to this change of split"
              disabled={disabled}
              testId="ledger-confirm"
              onClick={onConfirm}
            />
          )}
          {event.canUnconfirm && (
            <RowActionButton
              icon={Undo2}
              tooltip={t('pots.ledger.actions.unconfirm')}
              ariaLabel="Withdraw agreement"
              variant="muted"
              disabled={disabled}
              testId="ledger-unconfirm"
              onClick={onUnconfirm}
            />
          )}
          {event.canDelete && (
            <RowActionButton
              icon={Trash2}
              tooltip={t('pots.ledger.deleteTitle')}
              ariaLabel="Delete ledger entry"
              variant="destructive"
              disabled={disabled}
              testId="ledger-delete"
              onClick={onDelete}
            />
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
