'use client';

import Link from 'next/link';
import { History } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { EmptyState } from '@/components/empty-state';
import { SectionHeader } from '@/components/section-header';
import type { ActivityEntry } from '@/lib/api/group-activity';
import { useFormatters } from '@/lib/i18n/formatters';
import { activityRow } from '@/lib/shared-activity';

interface GroupActivitySectionProps {
  groupId: number;
  entries: ActivityEntry[];
}

/*
 * What has happened in this group, newest first: every act on a shared entity, who did it and when.
 *
 * A list rather than a table, unlike every other section on this page, and that follows from what an
 * entry IS. The four sections above are rows of one shape with columns worth comparing; an entry is a
 * sentence, and the sentences differ per action — a column headed "amount" would be empty for most of
 * them.
 *
 * Entries about a pot the reader cannot see are simply absent. That is the row-level policy's answer
 * rather than a filter here, so this section can never state more than the pot pages themselves would.
 */
export function GroupActivitySection({ groupId, entries }: GroupActivitySectionProps) {
  const t = useTranslations('shared');

  return (
    <div className="flex flex-col gap-y-4">
      <SectionHeader title={t('activity.title')} description={t('activity.description')} />
      {entries.length === 0 ? (
        <EmptyState
          icon={History}
          title={t('activity.emptyTitle')}
          description={t('activity.emptyDescription')}
        />
      ) : (
        <ol className="flex flex-col border border-border rounded-1.5xl">
          {entries.map((entry) => (
            <ActivityLine key={entry.id} entry={entry} groupId={groupId} />
          ))}
        </ol>
      )}
    </div>
  );
}

function ActivityLine({ entry, groupId }: { entry: ActivityEntry; groupId: number }) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  /*
   * The code is appended to every figure, because one group's trail holds every currency it has used
   * side by side and unconverted — a bare 120 beside a bare 90.000 leaves the reader to guess which is
   * dollars. Same rule the grouped list pages follow.
   */
  const row = activityRow(entry, groupId, {
    formatAmount: (amount, currency) => `${fmt.amount(amount, currency)} ${currency}`.trim(),
    potFallback: tCommon('potDefaultLabel'),
    unknownActor: t('activity.unknownActor'),
  });

  /*
   * The ROW carries the rounding and the link inherits it, so only the first and last corners round and
   * a middle row's hover tint is square — matching the container instead of drawing four rounded
   * corners in the middle of a list. NOT `overflow-hidden` on the list, which would clip the focus ring
   * (a box-shadow) off the top and bottom rows, hiding the keyboard cue exactly where it is hardest to
   * notice missing.
   */
  return (
    <li className="border-b border-border rounded-none first:rounded-t-1.5xl last:rounded-b-1.5xl last:border-b-0">
      {/*
       * A focusable SURFACE, so it takes the ring rather than the focus-bump family — and the ring is
       * what makes the keyboard cue DISTINCT from the hover tint, which is the half a background-only
       * treatment gets wrong: tabbing to a row would have looked exactly like pointing at it.
       */}
      <Link
        href={row.href}
        className="flex items-baseline justify-between px-4 py-3 gap-x-4 hover:bg-muted/40 rounded-[inherit] outline-none focus-visible:ring-3 focus-visible:ring-ring/50 transition-colors"
      >
        <span className="text-paragraph-sm">
          {t(`activity.entries.${row.textKey}`, row.params)}
        </span>
        <span className="shrink-0 text-paragraph-xs text-muted-foreground tabular-nums">
          {fmt.timestampDate(entry.createdAt)}
        </span>
      </Link>
    </li>
  );
}
