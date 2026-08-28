'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Scale, Shuffle, TrendingUp, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import {
  canRecordMovement,
  canRecordOpening,
  canRecordReagreement,
  hasLedger,
} from '@/app/(protected)/shared/pot-rules';
import { PotMovementDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-movement-dialog';
import { PotOpeningDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-opening-dialog';
import { PotReagreementDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-reagreement-dialog';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { Pot, PotHoldings, PotOwnershipEvent } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface PotOwnershipSectionProps {
  pot: Pot;
  group: Group;
  events: PotOwnershipEvent[];
  holdings: PotHoldings;
  privateAccounts: Account[];
  timeZone?: string;
}

/*
 * Who owns what, and the three ways that changes.
 *
 * Every member who may see the pot sees the whole breakdown, including one holding 0% of it (V5) —
 * partial visibility of something you co-own is not a feature, and this is the monitoring surface the
 * whole model exists for.
 *
 * The percentages here always sum to exactly 100 and the values to exactly the pot's, because the
 * backend assigns its rounding remainder to the largest holder. They are rendered at two decimals for
 * the same reason: at one, a three-way split reads 33.3 / 33.3 / 33.3 and visibly fails to add up.
 *
 * The three write controls are separately gated because they are separately possible: the baseline
 * exists exactly once and is impossible afterwards, a movement needs a price, and a re-agreement needs
 * a holder and someone to give to. One flag for all three would offer at least one of them wrongly.
 */
export function PotOwnershipSection({
  pot,
  group,
  events,
  holdings,
  privateAccounts,
  timeZone,
}: PotOwnershipSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const router = useRouter();
  const [openingOpen, setOpeningOpen] = useState(false);
  const [movementOpen, setMovementOpen] = useState(false);
  const [reagreementOpen, setReagreementOpen] = useState(false);

  const activeSeats = group.members.filter((m) => m.isActive).length;
  const refresh = () => router.refresh();

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader
          title={t('pots.ownership.title')}
          description={t('pots.ownership.description')}
        />
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {canRecordOpening(pot, events) && (
            <Button blue onClick={() => setOpeningOpen(true)}>
              <Scale className="size-4" />
              {t('pots.opening.cta')}
            </Button>
          )}
          {canRecordMovement(pot) && (
            <Button blue onClick={() => setMovementOpen(true)}>
              <TrendingUp className="size-4" />
              {t('pots.movement.cta')}
            </Button>
          )}
          {canRecordReagreement(pot, activeSeats) && (
            <Button variant="outline" onClick={() => setReagreementOpen(true)}>
              <Shuffle className="size-4" />
              {t('pots.reagreement.cta')}
            </Button>
          )}
        </div>
      </div>

      {pot.shares.length === 0 ? (
        <EmptyState
          icon={Users}
          title={t('pots.ownership.emptyTitle')}
          description={
            hasLedger(events)
              ? t('pots.ownership.emptyDescriptionBoughtOut')
              : t('pots.ownership.emptyDescription')
          }
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('pots.ownership.table.member')}</TableHead>
              <TableHead className="w-32 text-right">{t('pots.ownership.table.share')}</TableHead>
              <TableHead className="w-44 text-right">{t('pots.ownership.table.value')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pot.shares.map((share) => (
              <TableRow key={share.memberId}>
                <TableCell className="text-paragraph-sm-medium">
                  <span className="flex flex-wrap items-center gap-x-2">
                    {share.displayName}
                    {share.isSelf && <Badge variant="secondary">{t('pots.ownership.you')}</Badge>}
                  </span>
                </TableCell>
                <TableCell className="text-right text-paragraph-sm tabular-nums">
                  {`${fmt.sharePct(Number(share.percentage))}%`}
                </TableCell>
                <TableCell className="text-right text-paragraph-sm tabular-nums">
                  {/* Null when the pot has no valuation — a share of an unvalued pot is a real share
                      of an unknown amount, not a share worth nothing. */}
                  {share.value === null
                    ? t('pots.unvalued')
                    : fmt.amount(share.value, pot.baseCurrency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <PotOpeningDialog
        open={openingOpen}
        onOpenChange={setOpeningOpen}
        pot={pot}
        group={group}
        timeZone={timeZone}
        onSuccess={refresh}
      />
      <PotMovementDialog
        open={movementOpen}
        onOpenChange={setMovementOpen}
        pot={pot}
        group={group}
        holdings={holdings}
        privateAccounts={privateAccounts}
        timeZone={timeZone}
        onSuccess={refresh}
      />
      <PotReagreementDialog
        open={reagreementOpen}
        onOpenChange={setReagreementOpen}
        pot={pot}
        group={group}
        timeZone={timeZone}
        onSuccess={refresh}
      />
    </div>
  );
}
