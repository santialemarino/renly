import type { CSSProperties, ReactNode } from 'react';

import { cn } from '@repo/ui/lib';

interface MoneyFigureProps {
  // The formatted figure — `fmt.value(...)` / `fmt.amount(...)` — together with any sign or currency
  // code shown with it, which belong INSIDE: they are part of what the reader must see whole.
  children: ReactNode;
  className?: string;
  // Only `MetricCard` sets one: its fitted font size (see `metric-card.tsx`).
  style?: CSSProperties;
}

/*
 * Every standalone money figure the app renders goes through this, and two things follow from that.
 *
 * `data-money` marks it, so the e2e overflow sweep can find every figure on a page without knowing any
 * page's markup — a figure clipped by its card reads as a DIFFERENT number ("5,296,553." for
 * 5,296,553.12), with no ellipsis to say anything is missing. And `whitespace-nowrap` keeps it whole: a
 * figure never breaks across lines, since the two halves read as two amounts.
 */
export function MoneyFigure({ children, className, style }: MoneyFigureProps) {
  return (
    <span data-money="" className={cn('whitespace-nowrap tabular-nums', className)} style={style}>
      {children}
    </span>
  );
}
