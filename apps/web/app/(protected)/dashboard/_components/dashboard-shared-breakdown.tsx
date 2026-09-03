'use client';

import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { InlineLink } from '@/components/inline-link';
import { ROUTES, sharedPotPath } from '@/config/routes';
import type { DashboardOverview } from '@/lib/api/dashboard';
import { useFormatters } from '@/lib/i18n/formatters';
import { potLabel } from '@/lib/pots';

interface DashboardSharedBreakdownProps {
  overview: DashboardOverview;
}

/*
 * What the headline is made of, for somebody who shares money with other people.
 *
 * X1's rule in a block: your share of a co-owned asset genuinely is yours, so the figure above still
 * answers "what am I worth" — and this says how much of it is held in your own name and how much
 * through a group. Rendered ONLY when the user has a shared side at all, so a solo user's dashboard is
 * exactly what it was before this existed.
 *
 * The owed lines appear only when there is something owed, and they are kept apart rather than netted:
 * a receivable is an asset and a payable is a liability (D3), and somebody owed 100 in one group while
 * owing 100 in another is not somebody with no balances.
 *
 * The last lines are what stop a figure quietly disappearing. A pot whose owners have not agreed a
 * division yet contributes exactly zero to everybody — nobody owns any share of anything before the
 * baseline — so moving your own holding into a fresh pot drops it out of the headline. Naming the pot,
 * with a link to finish the setup, is what turns that from a bug report into an instruction.
 *
 * Both links are `InlineLink` rather than styled anchors, which is not a tidiness point: a hand-rolled
 * one here had its focus-visible colour lose to the muted base class and never fired the focus bump, so
 * tabbing through the card showed nothing at all. The shared component owns the underline, the bump and
 * the keyboard/hover parity.
 */
export function DashboardSharedBreakdown({ overview }: DashboardSharedBreakdownProps) {
  const fmt = useFormatters();
  const t = useTranslations('dashboard');
  const tCommon = useTranslations('common');

  if (!overview.hasShared) return null;

  return (
    <div className="flex flex-col pt-2 gap-y-1 border-t border-border-3">
      <SharedLine label={t('shared.yours')} value={fmt.value(overview.privateNetWorth)} />
      <SharedLine
        label={
          <InlineLink href={ROUTES.shared} color="muted" className="text-paragraph-xs">
            {t('shared.shared')}
          </InlineLink>
        }
        value={fmt.value(overview.sharedNetWorth)}
      />

      {overview.sharedReceivable !== 0 && (
        <SharedLine
          label={t('shared.owedToYou')}
          value={fmt.value(overview.sharedReceivable)}
          muted
        />
      )}
      {overview.sharedPayable !== 0 && (
        <SharedLine label={t('shared.youOwe')} value={fmt.value(overview.sharedPayable)} muted />
      )}

      {overview.undividedPots.map((pot) => (
        <InlineLink
          key={pot.potId}
          href={sharedPotPath(pot.potId)}
          color="muted"
          className="text-paragraph-mini"
        >
          {t('shared.undividedPot', {
            pot: potLabel(pot, tCommon('potDefaultLabel')),
            group: pot.groupName ?? '',
          })}
        </InlineLink>
      ))}
    </div>
  );
}

/*
 * One label/figure row of the breakdown. Extracted because four of them differ only in their words, and
 * the label is a node rather than a string so one of them can be a link without a second layout.
 *
 * It WRAPS rather than justifying, and that is load-bearing at this width: the card gives the block
 * about 140px, and a Spanish label beside a peso figure ("Compartido" + "1.313.438,08") needs 154 — so
 * a justify-between row silently overlapped the two, printing "Compartid1.313.438,08". Wrapping puts
 * the figure on its own line, still right-aligned by `ml-auto`, instead of truncating a ten-letter word
 * or hiding a digit of somebody's money.
 */
function SharedLine({
  label,
  value,
  muted,
}: {
  label: React.ReactNode;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2">
      <span className="text-paragraph-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          'ml-auto shrink-0 tabular-nums',
          muted ? 'text-paragraph-mini text-muted-foreground' : 'text-paragraph-xs-medium',
        )}
      >
        {value}
      </span>
    </div>
  );
}
