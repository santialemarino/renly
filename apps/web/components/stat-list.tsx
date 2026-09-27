import type { ReactNode } from 'react';

import { cn } from '@repo/ui/lib';

/*
 * Columns per row, stepped on the LIST's own width (`@container`), not the viewport's — the same rule
 * `MetricCardGrid` follows, for the same reason. The sidebar takes 15rem from the viewport at `md`, so
 * a `sm:grid-cols-3` put a twelve-digit balance in a 128px column at 768px, where it ran out over the
 * next stat. Each step leaves a column wide enough for such a figure at `text-paragraph-medium`.
 */
const STAT_LIST_COLUMNS = {
  3: '@2xl:grid-cols-3',
  4: '@xl:grid-cols-2 @4xl:grid-cols-4',
} as const;

export interface Stat {
  label: string;
  // A money figure here goes through `MoneyFigure`, like anywhere else.
  value: ReactNode;
}

interface StatListProps {
  stats: Stat[];
  columns: keyof typeof STAT_LIST_COLUMNS;
  // The panel around the list, which differs by surface (a tinted box, or none inside a card).
  className?: string;
}

// A labelled row of figures under a page or card header: the ledger's, a pot's, a group's only pot.
export function StatList({ stats, columns, className }: StatListProps) {
  return (
    <div className="@container">
      <dl className={cn('grid grid-cols-1 gap-x-6 gap-y-4', STAT_LIST_COLUMNS[columns], className)}>
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-y-1">
            <dt className="text-paragraph-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-paragraph-medium tabular-nums text-foreground">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
