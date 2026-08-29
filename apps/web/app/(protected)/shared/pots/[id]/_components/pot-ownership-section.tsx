'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, HandCoins, Scale, Shuffle, TrendingUp, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
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
  canTakeShareOut,
  hasLedger,
} from '@/app/(protected)/shared/pot-rules';
import { PotMovementDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-movement-dialog';
import { PotOpeningDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-opening-dialog';
import { PotReagreementDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-reagreement-dialog';
import { ComboboxChevron } from '@/components/combobox-chevron';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import { sharedBuyOutPath, sharedSharePath, sharedTakeOutPath } from '@/config/routes';
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
 * The guided flows LEAD and the raw actions sit behind a disclosure, which is U6's whole point: the
 * things people actually want to do — share something, take a share out, buy someone out — should not
 * be a sequence of primitives they assemble. The primitives stay reachable because several real cases
 * have no guided form: recording someone ELSE's contribution, moving only part of a share, correcting
 * a mistake. Removing them would take those away rather than simplify them.
 *
 * Every control is separately gated because each is separately possible: the baseline exists exactly
 * once and is impossible afterwards, a movement needs a price, and a re-agreement needs a holder and
 * someone to give to. One flag for all of them would offer at least one wrongly.
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
  const [manualOpen, setManualOpen] = useState(false);

  const activeSeats = group.members.filter((m) => m.isActive).length;
  const refresh = () => router.refresh();

  // Whether the disclosure has anything to disclose. Without this it would open onto nothing for a
  // read-only viewer, who has no write controls at all.
  const hasManualActions =
    canRecordOpening(pot, events) ||
    canRecordMovement(pot) ||
    canRecordReagreement(pot, activeSeats);

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader
          title={t('pots.ownership.title')}
          description={t('pots.ownership.description')}
        />
        {/*
         * The guided flows, as links rather than dialogs: they are routes, which is what lets each one
         * resume from what the server already has after a failure or a closed tab.
         */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {canRecordOpening(pot, events) && (
            <Button blue asChild>
              <Link href={sharedSharePath(pot.groupId, pot.id)}>
                <HandCoins className="size-4" />
                {t('pots.share.cta')}
              </Link>
            </Button>
          )}
          {canTakeShareOut(pot) && (
            <Button blue asChild>
              <Link href={sharedTakeOutPath(pot.id)}>
                <ArrowRight className="size-4" />
                {t('pots.takeOut.cta')}
              </Link>
            </Button>
          )}
          {canRecordReagreement(pot, activeSeats) && (
            <Button variant="outline" asChild>
              <Link href={sharedBuyOutPath(pot.id)}>
                <Shuffle className="size-4" />
                {t('pots.buyOut.cta')}
              </Link>
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

      {/*
       * The raw actions, one level down. Same three controls, same gates — only their prominence
       * changes, because assembling them is what U6 says a person should not have to do.
       */}
      {hasManualActions && (
        <Collapsible open={manualOpen} onOpenChange={setManualOpen}>
          <CollapsibleTrigger className="group/manual flex items-center gap-x-2 outline-none transition-colors hover:text-foreground focus-visible:text-foreground text-paragraph-sm-medium text-muted-foreground">
            <ComboboxChevron
              open={manualOpen}
              className="group-focus-visible/manual:text-foreground"
            />
            {t('pots.ownership.manual.title')}
          </CollapsibleTrigger>
          <CollapsibleContent className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
            <div className="flex flex-col mt-3 gap-y-3">
              <p className="text-paragraph-xs text-muted-foreground">
                {t('pots.ownership.manual.hint')}
              </p>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                {canRecordOpening(pot, events) && (
                  <Button variant="outline" onClick={() => setOpeningOpen(true)}>
                    <Scale className="size-4" />
                    {t('pots.opening.cta')}
                  </Button>
                )}
                {canRecordMovement(pot) && (
                  <Button variant="outline" onClick={() => setMovementOpen(true)}>
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
          </CollapsibleContent>
        </Collapsible>
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
