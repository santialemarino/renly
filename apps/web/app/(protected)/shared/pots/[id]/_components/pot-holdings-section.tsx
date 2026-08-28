'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Coins, Minus, Plus } from 'lucide-react';
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
import { canMoveHoldingsIn, canMoveHoldingsOut } from '@/app/(protected)/shared/pot-rules';
import { PotHoldingsDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-holdings-dialog';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import type { Account } from '@/lib/api/accounts';
import type { Investment } from '@/lib/api/investments';
import type { Pot, PotHolding, PotHoldings, PotOwnershipEvent } from '@/lib/api/pots';
import { useFormatters } from '@/lib/i18n/formatters';

interface PotHoldingsSectionProps {
  pot: Pot;
  holdings: PotHoldings;
  events: PotOwnershipEvent[];
  privateAccounts: Account[];
  privateInvestments: Investment[];
}

/*
 * What the pot actually holds — the investments and cash accounts whose combined value IS the pot's.
 *
 * Taking one out is offered only while nothing has been divided. Afterwards it would drop the pot's
 * value by the whole of that holding while nobody's units change, so every co-owner's share falls
 * pro-rata and it lands wholly in one person's private scope. Once ownership is agreed, taking value
 * out is a withdrawal, which redeems units and says whose money it was.
 */
export function PotHoldingsSection({
  pot,
  holdings,
  events,
  privateAccounts,
  privateInvestments,
}: PotHoldingsSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [addOpen, setAddOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);

  const isEmpty = holdings.investments.length === 0 && holdings.accounts.length === 0;
  const refresh = () => router.refresh();

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader
          title={t('pots.holdings.title')}
          description={t('pots.holdings.description')}
        />
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {canMoveHoldingsIn(pot) && (
            <Button blue onClick={() => setAddOpen(true)}>
              <Plus className="size-4" />
              {t('pots.holdings.addCta')}
            </Button>
          )}
          {/*
           * Hidden rather than disabled once the ledger exists: a Radix tooltip never fires on a
           * disabled trigger, so the explanation would be unreadable. The reason lives in the section
           * description, and the supported action (a withdrawal) is one section up.
           */}
          {!isEmpty && canMoveHoldingsOut(pot, events) && (
            <Button variant="outline" onClick={() => setRemoveOpen(true)}>
              <Minus className="size-4" />
              {t('pots.holdings.removeCta')}
            </Button>
          )}
        </div>
      </div>

      {isEmpty ? (
        <EmptyState
          icon={Coins}
          title={t('pots.holdings.emptyTitle')}
          description={
            pot.canWrite
              ? t('pots.holdings.emptyDescription')
              : t('pots.holdings.emptyDescriptionReadOnly')
          }
        />
      ) : (
        <div className="flex flex-col gap-y-6">
          {holdings.investments.length > 0 && (
            <HoldingsTable
              caption={t('pots.holdings.investments')}
              holdings={holdings.investments}
              baseCurrency={pot.baseCurrency}
            />
          )}
          {holdings.accounts.length > 0 && (
            <HoldingsTable
              caption={t('pots.holdings.accounts')}
              holdings={holdings.accounts}
              baseCurrency={pot.baseCurrency}
            />
          )}
        </div>
      )}

      <PotHoldingsDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        pot={pot}
        into
        holdings={holdings}
        privateInvestments={privateInvestments}
        privateAccounts={privateAccounts}
        onSuccess={refresh}
      />
      <PotHoldingsDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        pot={pot}
        into={false}
        holdings={holdings}
        privateInvestments={privateInvestments}
        privateAccounts={privateAccounts}
        onSuccess={refresh}
      />
    </div>
  );
}

/*
 * One kind of holding. Two figures per row because they answer different questions: what the holding is
 * worth in its own currency, and what it contributes to a pot denominated in another. The second column
 * only appears when at least one row is in a different currency — otherwise it repeats the first.
 */
function HoldingsTable({
  caption,
  holdings,
  baseCurrency,
}: {
  caption: string;
  holdings: PotHolding[];
  baseCurrency: string;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const showBase = holdings.some((holding) => holding.currency !== baseCurrency);

  return (
    <div className="flex flex-col gap-y-2">
      <h3 className="text-paragraph-sm-semibold text-foreground">{caption}</h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('pots.holdings.table.name')}</TableHead>
            <TableHead className="w-44 text-right">{t('pots.holdings.table.value')}</TableHead>
            {showBase && (
              <TableHead className="w-44 text-right">
                {t('pots.holdings.table.inBaseCurrency', { currency: baseCurrency })}
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {holdings.map((holding) => (
            <TableRow key={holding.id}>
              <TableCell className="text-paragraph-sm-medium">
                <span className="flex flex-wrap items-center gap-x-2">
                  {holding.name}
                  <Badge variant="secondary">{holding.currency}</Badge>
                  {/* An archived holding is listed because it still blocks deleting the pot and still
                      has to be movable out — but it contributes nothing to the pot's value, so the
                      badge is what stops its figure from reading as part of the total. */}
                  {!holding.isActive && (
                    <Badge variant="secondary">{t('pots.holdings.archived')}</Badge>
                  )}
                </span>
              </TableCell>
              <TableCell className="text-right text-paragraph-sm tabular-nums">
                {/* Null means nobody has valued it yet — a pot can legitimately hold something with no
                    snapshot, and rendering that as 0 would assert a value the data does not have. */}
                {holding.value === null
                  ? t('pots.unvalued')
                  : fmt.amount(holding.value, holding.currency)}
              </TableCell>
              {showBase && (
                <TableCell className="text-right text-paragraph-sm tabular-nums text-muted-foreground">
                  {holding.baseValue === null
                    ? t('pots.unvalued')
                    : fmt.amount(holding.baseValue, baseCurrency)}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
