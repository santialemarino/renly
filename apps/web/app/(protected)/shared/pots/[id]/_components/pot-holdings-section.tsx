'use client';

import { useState } from 'react';
import Link from 'next/link';
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
import {
  canContributeHolding,
  canMoveHoldingsIn,
  canMoveHoldingsOut,
  hasLedger,
} from '@/app/(protected)/shared/pot-rules';
import { PotHoldingsDialog } from '@/app/(protected)/shared/pots/[id]/_components/pot-holdings-dialog';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import { sharedContributePath } from '@/config/routes';
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
 * Neither direction is offered as a PLAIN move once ownership is agreed, and the two are refused for
 * opposite reasons. Taking one out would drop the pot's value by the whole of that holding while
 * nobody's units change, so every co-owner's share falls pro-rata and it lands wholly in one person's
 * private scope. Putting one in is the mirror: the value RISES with nobody's units changing, so what
 * one person added out of their own scope is gifted pro-rata to everybody.
 *
 * Adding is still available afterwards, priced — the button becomes the contribution flow rather than
 * disappearing, which is the difference between an act that is unsupported and one that has a
 * different shape. Taking value out has no such counterpart here: it is a withdrawal or a buy-out, one
 * section up, because what leaves a divided pot is a SHARE rather than a thing.
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
          /*
           * The description says WHY both buttons are gone once ownership is agreed, rather than the
           * section going silent about it: hiding an action without saying why leaves somebody looking
           * for a control that used to be there. It names the supported acts in the same sentence.
           */
          description={
            hasLedger(events)
              ? `${t('pots.holdings.description')} ${t('pots.holdings.dividedNote')}`
              : t('pots.holdings.description')
          }
        />
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {/*
           * The same act, two shapes, and which one is offered turns on whether there is a unit price
           * to issue against. Before the split a plain move is free — nothing has been divided, so
           * nothing can be given away. After it, the value has to buy units or it is a silent gift, so
           * the control becomes the guided flow.
           *
           * A LINK rather than a button with a router.push: it navigates and nothing else, so
           * new-tab, middle-click and "link" in a screen reader's list all have to keep working.
           */}
          {canMoveHoldingsIn(pot, events) ? (
            <Button blue onClick={() => setAddOpen(true)}>
              <Plus className="size-4" />
              {t('pots.holdings.addCta')}
            </Button>
          ) : (
            canContributeHolding(pot) && (
              <Button blue asChild>
                <Link href={sharedContributePath(pot.id)} data-testid="pot-contribute-cta">
                  <Plus className="size-4" />
                  {t('pots.holdings.contributeCta')}
                </Link>
              </Button>
            )
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
            !pot.canWrite
              ? t('pots.holdings.emptyDescriptionReadOnly')
              : canMoveHoldingsIn(pot, events)
                ? t('pots.holdings.emptyDescription')
                : // An empty pot that is already divided is a real state — every holding was moved out
                  // before the baseline, or the pot was created for a division of value held elsewhere
                  // — and the generic "add one" line describes the wrong control.
                  t('pots.holdings.emptyDescriptionDivided')
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
 *
 * The "valued" column is what the header's freshness line points AT. The pot is only as current as its
 * stalest holding, so a pot reading overdue needs to say which row is responsible — otherwise the
 * reader is told there is a problem and left to guess where. It appears only for rows that HAVE a
 * valuation date, which is the investments: an account's balance is derived at the moment it is asked
 * for, so it has no recorded date and can never be the stale one.
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
  const showValuedOn = holdings.some((holding) => holding.valuedOn !== null);

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
            {showValuedOn && (
              <TableHead className="w-36 text-right">{t('pots.holdings.table.valuedOn')}</TableHead>
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
              {showValuedOn && (
                <TableCell className="text-right text-paragraph-sm tabular-nums text-muted-foreground">
                  {/* A null reaching a RENDERED cell always means "never valued": the column only
                      appears when some holding in this table has a date, and only an investment ever
                      has one — an account's balance is derived, so its table never shows the column
                      at all. A dash rather than words, because the value cell beside it already
                      says "not valued yet" and repeating it twice per row says nothing extra. */}
                  {holding.valuedOn === null ? '—' : fmt.date(holding.valuedOn)}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
