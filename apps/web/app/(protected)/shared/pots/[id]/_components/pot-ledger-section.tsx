'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { History, Trash2 } from 'lucide-react';
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
import { deletePotOwnershipEvent } from '@/app/(protected)/shared/pot-actions';
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

  async function onDelete() {
    if (!pendingDelete) return;
    setPending(true);
    try {
      const result = await deletePotOwnershipEvent(pot.id, pendingDelete.id);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(
        t(isBaseline ? 'pots.ledger.deleteBaselineSuccess' : 'pots.ledger.deleteSuccess'),
      );
      router.refresh();
    } catch {
      toast.error(t('pots.ledger.deleteError'));
    } finally {
      setPending(false);
      setDeleteOpen(false);
    }
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
              <TableHead className="w-20 text-center">{t('pots.ledger.table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((event) => (
              <LedgerRow
                key={event.id}
                pot={pot}
                event={event}
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
  onDelete,
}: {
  pot: Pot;
  event: PotOwnershipEvent;
  onDelete: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const figure = ownershipEventAmount(event, pot.baseCurrency);

  return (
    <TableRow>
      <TableCell className="text-paragraph-sm tabular-nums">{fmt.date(event.date)}</TableCell>
      <TableCell>
        <Badge variant="secondary">{t(`pots.eventTypes.${event.type}`)}</Badge>
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
        {pot.canWrite && (
          <RowActionButton
            icon={Trash2}
            tooltip={t('pots.ledger.deleteTitle')}
            ariaLabel="Delete ledger entry"
            variant="destructive"
            onClick={onDelete}
          />
        )}
      </TableCell>
    </TableRow>
  );
}
