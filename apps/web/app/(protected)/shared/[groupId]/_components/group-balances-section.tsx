'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { HandCoins, Scale, SlidersHorizontal, XCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Badge, Button } from '@repo/ui/components';
import { GroupMoneySettingsDialog } from '@/app/(protected)/shared/[groupId]/_components/group-money-settings-dialog';
import { SettlementFormDialog } from '@/app/(protected)/shared/[groupId]/_components/settlement-form-dialog';
import { WriteOffDialog } from '@/app/(protected)/shared/[groupId]/_components/write-off-dialog';
import {
  balanceMagnitude,
  balancesEmptyState,
  balanceStanding,
  canWriteOffSuggestion,
  hasOpenBalances,
  suggestionVoice,
} from '@/app/(protected)/shared/settlement-rules';
import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import type { Account } from '@/lib/api/accounts';
import type {
  GroupBalances,
  GroupCurrencyBalance,
  GroupMoneySettings,
  GroupSettleSuggestion,
} from '@/lib/api/group-settlements';
import type { Group } from '@/lib/api/groups';
import { useFormatters } from '@/lib/i18n/formatters';

interface GroupBalancesSectionProps {
  group: Group;
  balances: GroupBalances;
  // Whether the group has recorded any shared expense at all, which is what tells "nobody has shared
  // anything" apart from "everyone is square" — two opposite sentences for the same empty list.
  hasSharedSpending: boolean;
  // Null when the settings could not be read. The control that edits them is then not offered rather
  // than opened on invented defaults — a dialog that saves what it guessed would overwrite the real
  // values with them.
  moneySettings: GroupMoneySettings | null;
  accounts: Account[];
  timeZone?: string;
}

/*
 * Where the group stands, one currency at a time.
 *
 * The buckets never net against each other, and the section is shaped so they cannot appear to: each
 * currency gets its own block, its own positions and its own settle lines. Owing dollars while being
 * owed pesos is a real, common state, and one merged figure would invent a rate nobody agreed to.
 *
 * Each block shows the same facts twice on purpose — every member's standing, and then the fewest
 * payments that would clear it. They are two views of one arithmetic (the positions sum to zero, and
 * the plan moves exactly those positions to zero), so they must agree on screen; a reader checks one
 * against the other, which is precisely what makes the pair worth rendering together.
 *
 * The converted figure beside a bucket is for reading at a glance and is never what anybody settles —
 * so it sits with the viewer's own standing, in words, rather than beside the amounts people pay.
 */
export function GroupBalancesSection({
  group,
  balances,
  hasSharedSpending,
  moneySettings,
  accounts,
  timeZone,
}: GroupBalancesSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const router = useRouter();
  const [settling, setSettling] = useState<{
    suggestion: GroupSettleSuggestion;
    currency: string;
  } | null>(null);
  const [writingOff, setWritingOff] = useState<{
    suggestion: GroupSettleSuggestion;
    currency: string;
  } | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const mySeatId = useMemo(
    () => group.members.find((member) => member.isSelf)?.id ?? null,
    [group.members],
  );

  const isAdmin = group.myRole === 'admin';
  const refresh = () => router.refresh();

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader title={t('balances.title')} description={t('balances.description')} />
        {/* The two standards the whole money block runs on, so the control sits at its top. Admin
            only, matching the API — setting them is management, not money movement. */}
        {isAdmin && moneySettings && (
          <Button variant="outline" onClick={() => setSettingsOpen(true)}>
            <SlidersHorizontal className="size-4" />
            {t('moneySettings.open')}
          </Button>
        )}
      </div>

      {/*
       * The buckets the glance figure could not be converted into. Said out loud rather than left as
       * a silently absent parenthetical: the bucket itself is entirely correct — only the
       * at-a-glance conversion is missing — and a reader who sees one bucket carry the aside and
       * another not deserves the reason rather than a guess.
       */}
      {balances.displayCurrency !== null && balances.skippedCurrencies.length > 0 && (
        <p className="text-paragraph-xs text-muted-foreground">
          {t('balances.skipped', {
            currency: balances.displayCurrency,
            currencies: fmt.list(balances.skippedCurrencies),
          })}
        </p>
      )}

      {!hasOpenBalances(balances.buckets) ? (
        <EmptyState
          icon={Scale}
          title={t(`balances.empty.${balancesEmptyState(hasSharedSpending)}.title`)}
          description={t(`balances.empty.${balancesEmptyState(hasSharedSpending)}.description`)}
        />
      ) : (
        <div className="flex flex-col gap-y-4">
          {balances.buckets.map((bucket) => (
            <BucketCard
              key={bucket.currency}
              bucket={bucket}
              displayCurrency={balances.displayCurrency}
              mySeatId={mySeatId}
              onSettle={(suggestion) => setSettling({ suggestion, currency: bucket.currency })}
              onWriteOff={(suggestion) => setWritingOff({ suggestion, currency: bucket.currency })}
            />
          ))}
        </div>
      )}

      {/*
       * Both dialogs keep their data mounted through the close: `open` is toggled from the state and
       * the payload is passed as a stable prop, so the body does not blank out mid-animation.
       */}
      <SettlementFormDialog
        open={settling !== null}
        onOpenChange={(open) => !open && setSettling(null)}
        group={group}
        suggestion={settling?.suggestion}
        currency={settling?.currency ?? ''}
        accounts={accounts}
        timeZone={timeZone}
        onSuccess={refresh}
      />
      <WriteOffDialog
        open={writingOff !== null}
        onOpenChange={(open) => !open && setWritingOff(null)}
        groupId={group.id}
        suggestion={writingOff?.suggestion}
        currency={writingOff?.currency ?? ''}
        timeZone={timeZone}
        onSuccess={refresh}
      />
      {moneySettings && (
        <GroupMoneySettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          groupId={group.id}
          settings={moneySettings}
          onSuccess={refresh}
        />
      )}
    </div>
  );
}

/*
 * One currency's standing: who is up, who is down, and the fewest payments that clear it.
 *
 * Every member of the group may record a payment, which is the API's own rule — either side of one
 * can be the person who remembers to write it down. What the viewer's seat changes is emphasis, and
 * whether a write-off is offered at all: giving up a claim belongs to whoever holds it.
 */
function BucketCard({
  bucket,
  displayCurrency,
  mySeatId,
  onSettle,
  onWriteOff,
}: {
  bucket: GroupCurrencyBalance;
  displayCurrency: string | null;
  mySeatId: number | null;
  onSettle: (suggestion: GroupSettleSuggestion) => void;
  onWriteOff: (suggestion: GroupSettleSuggestion) => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const standing = balanceStanding(bucket.myBalance);
  /*
   * The at-a-glance figure, shown only when the viewer is browsing in a DIFFERENT currency from the
   * bucket's — an identical figure repeated would read as a second, separate fact.
   *
   * It names its currency, and has to: the figure beside it is in the bucket's currency and carries
   * no code of its own (the badge says which), so "≈ 32.48" next to "50,000" is two numbers in two
   * currencies with nothing on screen saying which is which.
   */
  const converted = bucket.myConvertedBalance;
  // Null when the viewer is browsing in this bucket's own currency, so the figure is never repeated.
  const glanceCurrency = displayCurrency === bucket.currency ? null : displayCurrency;
  const glance =
    converted !== null && glanceCurrency !== null
      ? {
          amount: fmt.amount(balanceMagnitude(converted), glanceCurrency),
          currency: glanceCurrency,
        }
      : null;

  return (
    <div className="flex flex-col p-4 gap-y-4 bg-muted/30 border border-border rounded-1.5xl">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="flex flex-wrap items-center gap-x-2">
          <Badge variant="secondary">{bucket.currency}</Badge>
          <span className="text-paragraph-medium text-foreground">
            {standing === 'square'
              ? t('balances.standing.square')
              : t(`balances.standing.${standing}`, {
                  amount: fmt.amount(balanceMagnitude(bucket.myBalance), bucket.currency),
                })}
          </span>
        </span>
        {glance !== null && (
          <span className="text-paragraph-xs text-muted-foreground">
            {t('balances.glance', glance)}
          </span>
        )}
      </div>

      {/*
       * Every member with an open position, largest creditor first — the API's own order, so the list
       * reads as a ranking rather than in seat order. A member who is square has no row: they have
       * nothing outstanding, and a line of zeros on every screen says nothing.
       */}
      <dl className="flex flex-col gap-y-2">
        {bucket.balances.map((balance) => {
          const memberStanding = balanceStanding(balance.amount);
          return (
            <div key={balance.memberId} className="flex items-baseline justify-between gap-x-3">
              <dt className="min-w-0 truncate text-paragraph-sm text-foreground">
                {balance.displayName}
                {balance.isSelf && (
                  <span className="text-paragraph-xs text-muted-foreground">
                    {' '}
                    {t('members.you')}
                  </span>
                )}
              </dt>
              <dd className="shrink-0 text-paragraph-sm tabular-nums text-muted-foreground">
                {t(`balances.position.${memberStanding}`, {
                  amount: fmt.amount(balanceMagnitude(balance.amount), bucket.currency),
                })}
              </dd>
            </div>
          );
        })}
      </dl>

      <div className="flex flex-col gap-y-2">
        <span className="text-paragraph-xs-medium text-muted-foreground">
          {t('balances.plan.title')}
        </span>
        {bucket.suggestions.map((suggestion) => (
          <div
            key={`${suggestion.fromMemberId}-${suggestion.toMemberId}`}
            className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3 py-2 bg-background border border-border rounded-lg"
          >
            <span className="min-w-0 text-paragraph-sm text-foreground">
              {t(`balances.plan.${suggestionVoice(suggestion, mySeatId)}`, {
                from: suggestion.fromDisplayName,
                to: suggestion.toDisplayName,
                amount: fmt.amount(suggestion.amount, bucket.currency),
              })}
            </span>
            <span className="flex shrink-0 items-center gap-x-2">
              {canWriteOffSuggestion(suggestion, mySeatId) && (
                <Button variant="outline" size="sm" onClick={() => onWriteOff(suggestion)}>
                  <XCircle className="size-4" />
                  {t('balances.plan.writeOff')}
                </Button>
              )}
              <Button blue size="sm" onClick={() => onSettle(suggestion)}>
                <HandCoins className="size-4" />
                {t('balances.plan.settle')}
              </Button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
