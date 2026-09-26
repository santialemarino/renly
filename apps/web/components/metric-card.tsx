'use client';

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

import { Card } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { MoneyFigure } from '@/components/money-figure';
import { useFormatters } from '@/lib/i18n/formatters';

/*
 * Columns per row, stepped on the width the GRID has rather than on the viewport's.
 *
 * The viewport is the wrong axis here: the sidebar takes 15rem from it at `md` and up, so a
 * `lg:grid-cols-5` handed five cards ~130px each at 1024px — narrower than an eight-digit figure — and
 * the digits past the card's edge were cut off by the page's `overflow-x-hidden`, printing
 * "5,296,553." for 5,296,553.12. Every step below leaves each card at least 256px, which is what a
 * thirteen-character figure ("-3,923,637.12", all digits at worst: 13 × 0.6em × 24px) needs at full
 * size beside its icon — measured, and held by the e2e money sweep at eight widths. A card count
 * without an entry here is a type error rather than an unconsidered layout.
 */
const METRIC_GRID_COLUMNS = {
  4: '@xl:grid-cols-2 @min-[67rem]:grid-cols-4',
  5: '@xl:grid-cols-2 @4xl:grid-cols-3 @min-[84rem]:grid-cols-5',
} as const;

// The icon's box plus the gap before it (`size-5` + `gap-x-2`), which the figure must leave free.
const METRIC_ICON_RESERVE = '1.75rem';

interface MetricCardGridProps {
  count: keyof typeof METRIC_GRID_COLUMNS;
  children: ReactNode;
  testId?: string;
}

// The row of headline cards at the top of a dashboard.
export function MetricCardGrid({ count, children, testId }: MetricCardGridProps) {
  return (
    <div className="@container">
      <div
        className={cn('grid grid-cols-1 gap-4', METRIC_GRID_COLUMNS[count])}
        data-testid={testId}
      >
        {children}
      </div>
    </div>
  );
}

// The headline figure: an amount (formatted and marked as money here, so a caller cannot forget
// either) or an already-formatted non-money text such as a return percentage.
type MetricFigure = { amount: number; text?: never } | { text: string; amount?: never };

type MetricCardProps = MetricFigure & {
  label: ReactNode;
  // Colour and similar for the figure; the size is the card's.
  figureClassName?: string;
  // Shown beside the figure (a trend arrow, a card icon), at the card's icon size; the caller colours it.
  icon?: LucideIcon;
  iconClassName?: string;
  // A short text beside the figure (a return percentage). Unlike the icon it has no fixed width, so it
  // gets no reserved room: when the figure needs the whole row, this wraps beneath it instead.
  trailing?: ReactNode;
  // Everything under the figure: the change line, the hint, a breakdown.
  children?: ReactNode;
};

/*
 * One headline card. The three dashboards had each hand-written the same card five, four and four
 * times, and all thirteen shared the defect — a `text-heading-3` figure with nothing to stop it running
 * past its card — so the figure's layout lives here once.
 *
 * The figure's row is the size container its `MoneyFigure fit` measures, and the figure keeps the icon's
 * room free inside it — so the icon stays beside the figure, and the room the figure has is the card's
 * width minus the icon's, whatever the grid gives the card. That is why the card owns the icon's size.
 */
export function MetricCard({
  label,
  amount,
  text,
  figureClassName,
  icon: Icon,
  iconClassName,
  trailing,
  children,
}: MetricCardProps) {
  const fmt = useFormatters();

  return (
    <Card compact>
      <span className="text-paragraph-sm text-muted-foreground">{label}</span>
      <div className="@container flex flex-wrap items-center gap-x-2">
        <p className={cn('min-w-0 text-heading-3', figureClassName)}>
          {amount !== undefined ? (
            <MoneyFigure fit fitReserve={Icon ? METRIC_ICON_RESERVE : undefined}>
              {fmt.value(amount)}
            </MoneyFigure>
          ) : (
            text
          )}
        </p>
        {Icon && <Icon className={cn('size-5 shrink-0', iconClassName)} />}
        {trailing}
      </div>
      {children}
    </Card>
  );
}
