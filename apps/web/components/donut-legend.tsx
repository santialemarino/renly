'use client';

import type { CSSProperties, ReactNode } from 'react';

import { useFormatters } from '@/lib/i18n/formatters';

export interface DonutLegendItem {
  key: string;
  name: string;
  color: CSSProperties['backgroundColor'];
  // Already in percent units (40 → "40%").
  percentage: number;
  // Anything shown after the percentage, e.g. a collection's target.
  extra?: ReactNode;
}

/*
 * A donut beside its legend when the CARD has room for both, the legend beneath it when it does not.
 *
 * Decided by the card's own width (`@container`), not the viewport's. The three donuts used `lg:` —
 * but at 1024px the sidebar and a sibling chart leave the card ~300px, so the fixed 240px donut took
 * almost all of it and the legend's names were truncated to nothing: a row of dots and percentages
 * with no category left to name. `@lg` (32rem) is the donut plus its gap plus a legend column wide
 * enough to hold a name.
 */
export function DonutLegendLayout({ legend, chart }: { legend: ReactNode; chart: ReactNode }) {
  return (
    <div className="@container">
      <div className="flex flex-col-reverse items-center gap-y-4 @lg:flex-row @lg:gap-x-6 @lg:gap-y-0">
        <div className="w-full @lg:min-w-0 @lg:flex-1">{legend}</div>
        {chart}
      </div>
    </div>
  );
}

/*
 * The legend of a donut: a colour, the full name, the share.
 *
 * The name WRAPS and is never truncated — identity must never be colour alone, and a truncated Spanish
 * category ("Comisiones e Impuestos de Tarjeta") is a name nobody can read. So it takes the free width
 * and breaks onto more lines (hyphenated by the page's `lang` where a single word is longer than the
 * column), and the list drops to one column in a card too narrow for two. The dot is pinned to the
 * first line so a wrapped name still reads as one entry. Must sit inside `DonutLegendLayout`, whose
 * container its column count steps on.
 */
export function DonutLegend({ items }: { items: DonutLegendItem[] }) {
  const fmt = useFormatters();

  return (
    <ul className="grid grid-cols-1 gap-x-4 gap-y-2 @sm:grid-cols-2 @lg:flex @lg:flex-col">
      {items.map((item) => (
        <li key={item.key} className="flex items-start gap-x-2">
          <span
            aria-hidden
            className="mt-1 size-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          <span
            className="flex-1 min-w-0 text-paragraph-xs text-muted-foreground wrap-break-word hyphens-auto"
            data-testid="chart-legend-label"
          >
            {item.name}
          </span>
          <span className="shrink-0 text-paragraph-xs-semibold">{fmt.pct(item.percentage)}%</span>
          {item.extra}
        </li>
      ))}
    </ul>
  );
}
