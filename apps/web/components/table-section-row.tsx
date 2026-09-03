'use client';

import { Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { TableCell, TableRow } from '@repo/ui/components';
import { InlineLink } from '@/components/inline-link';
import { sharedPotPath } from '@/config/routes';
import type { ListSection } from '@/lib/api/types';
import { useFormatters } from '@/lib/i18n/formatters';
import { potLabel } from '@/lib/pots';

/*
 * One labelled section header inside a scope-grouped table (X2). The same row on all five surfaces, so
 * the label, the count and the totals cannot drift between /investments, /accounts, /expenses, /income
 * and the snapshots grid.
 *
 * The label is `{pot} · {group}` where the list groups by pot, and the group's name alone where it
 * groups by a group — and `potLabel` supplies the fallback for a group's unnamed default pot, because
 * a null interpolated into copy fails by PRINTING rather than by raising.
 *
 * The totals are per CURRENCY and never netted, each with its code beside it: a section holding pesos
 * and dollars side by side has no single figure, and one blended number would hide which was which.
 * A section whose rows carry no money column (an investment has no value here) shows its count alone —
 * a header figure the visible rows cannot add up to is exactly what X2's grouping exists to avoid.
 */
export function TableSectionRow({
  section,
  colSpan,
  countLabel,
}: {
  section: ListSection;
  colSpan: number;
  // The already-translated row count, because the noun differs per list ("4 holdings", "12 expenses").
  countLabel: string;
}) {
  const fmt = useFormatters();
  const tCommon = useTranslations('common');

  const isShared = section.scope === 'shared';
  const potId = section.potId;
  /*
   * The label, and every branch of it is a defence against a null reaching copy.
   *
   * `potName` is legitimately null for a group's unnamed default pot (A4), so `potLabel` supplies the
   * fallback. `groupName` is non-null on a shared section by API contract — the service DROPS a pot it
   * cannot name — but a null interpolated into "{pot} · {group}" fails by PRINTING a dangling
   * separator rather than by raising, which is exactly the defect the notification layer shipped and
   * PR 8a caught a second time. So the paired form is used only when BOTH halves exist, and the last
   * fallback is a word rather than an empty header.
   */
  const potName =
    potId !== null ? potLabel({ name: section.potName }, tCommon('potDefaultLabel')) : null;
  const label =
    potName !== null && section.groupName !== null
      ? tCommon('scope.potInGroup', { pot: potName, group: section.groupName })
      : (potName ?? section.groupName ?? tCommon('scope.shared'));

  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className="bg-muted/40 py-2">
        {/*
         * STICKY to the left, and the whole content left-grouped rather than the figures pushed to
         * the far edge.
         *
         * The snapshots grid is what settles this: its table runs to a few thousand pixels, so an
         * `ml-auto` count sat past the right edge of a horizontally scrolling container and was
         * simply never seen. `w-fit` keeps the sticky box from spanning the full colSpan, which
         * would make `sticky` a no-op.
         */}
        <div className="sticky left-0 flex w-fit flex-wrap items-center gap-x-2 gap-y-1">
          {isShared && <Users className="size-3.5 shrink-0 text-muted-foreground" />}
          {!isShared ? (
            <span className="text-paragraph-sm-semibold">{tCommon('scope.private')}</span>
          ) : potId !== null ? (
            /* A pot-grouped section links to the pot, which is where every shared action lives. */
            <InlineLink
              href={sharedPotPath(potId)}
              color="brand"
              className="text-paragraph-sm-semibold"
            >
              {label}
            </InlineLink>
          ) : (
            <span className="text-paragraph-sm-semibold">{label}</span>
          )}
          <span className="flex flex-wrap items-center gap-x-3 text-paragraph-xs text-muted-foreground">
            <span>{countLabel}</span>
            {/*
             * Each total NAMES its currency, and that is the rule rather than a nicety: a section
             * that holds pesos and dollars prints both side by side and unconverted, so a bare
             * 1.452.000 beside a bare 200 leaves the reader to guess which one is dollars.
             */}
            {section.totals.map((total) => (
              <span key={total.currency} className="tabular-nums">
                {`${fmt.amount(total.amount, total.currency)} ${total.currency}`}
              </span>
            ))}
          </span>
        </div>
      </TableCell>
    </TableRow>
  );
}
