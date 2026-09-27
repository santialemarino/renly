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
 * "5,296,553." for 5,296,553.12. A thirteen-character figure ("-3,923,637.12") needs a card of 257.2px
 * at full size beside its icon: 187.2 of text at worst (13 × 0.6em × 24px) + 28 of icon and gap + 40
 * of padding + 2 of border. Every multi-column step below leaves each card at least 272px (the
 * narrowest measured, four cards at 1440px). The one-column layout at a 320px viewport gives 256px,
 * 1.2px short, where the fit below takes the figure from 24px to 23.85px — the one width at which a
 * typical figure is not at its full size. The e2e money sweep holds all of this at eight widths. A card
 * count without an entry here is a type error rather than an unconsidered layout.
 */
const METRIC_GRID_COLUMNS = {
  4: '@xl:grid-cols-2 @min-[67rem]:grid-cols-4',
  5: '@xl:grid-cols-2 @4xl:grid-cols-3 @min-[84rem]:grid-cols-5',
} as const;

// The icon's box plus the gap before it (`size-5` + `gap-x-2`), which the figure must leave free.
const METRIC_ICON_RESERVE = '1.75rem';

/*
 * The widest a headline figure's characters run, in ems of its own font size.
 *
 * Measured, not assumed: Plus Jakarta Sans with `tabular-nums` sets every digit at exactly 0.60em at
 * weights 400-600, and the group and decimal separators (0.27-0.35em) and the hyphen-minus Intl uses
 * (0.50-0.57em) are all narrower — so for what `fmt.value` produces, the character count times this is
 * an upper bound on the width, reached only by a figure that is all digits. It is NOT a bound for
 * letters or symbols (a currency code's "D" is 0.74em), which is one reason the fit lives here, where
 * the figure is always a bare `fmt.value`.
 */
const FIT_EM_PER_CHAR = 0.6;

/*
 * The fitted size of a headline figure: the card's own size (`1em`) until the figure would be wider
 * than the room its row leaves it, then just small enough to fit. When something has to give, it is
 * the type size, never a digit.
 *
 * PRIVATE to this card, not an option on `MoneyFigure`, because it is only correct against this card's
 * layout: `100cqi` measures the figure's ROW, which is a size container here, and the only thing
 * sharing that row with a known width is the icon, which is reserved. On a figure with no container
 * above it `cqi` falls back to the viewport and the fit silently does nothing; beside text of unknown
 * width it cannot know the room. A self-contained version would have to make the figure its own
 * container, which gives it no intrinsic width — so a sibling like the gain's return percentage could
 * no longer wrap beneath it, and the figure would shrink to share the line instead.
 */
function fittedSize(text: string, reserve: string | undefined) {
  const room = reserve ? `(100cqi - ${reserve})` : '100cqi';
  return { fontSize: `min(1em, calc(${room} / (${text.length} * ${FIT_EM_PER_CHAR})))` };
}

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
 * The figure's row is the size container its fitted size measures, and the figure keeps the icon's
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

  const figure = amount !== undefined ? fmt.value(amount) : undefined;

  return (
    <Card compact>
      <span className="text-paragraph-sm text-muted-foreground">{label}</span>
      <div className="@container flex flex-wrap items-center gap-x-2">
        <p className={cn('min-w-0 text-heading-3', figureClassName)}>
          {figure !== undefined ? (
            <MoneyFigure style={fittedSize(figure, Icon ? METRIC_ICON_RESERVE : undefined)}>
              {figure}
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
