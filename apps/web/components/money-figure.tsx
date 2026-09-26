import { Children, type CSSProperties, type ReactNode } from 'react';

import { cn } from '@repo/ui/lib';

/*
 * The widest a plain formatted figure's characters run, in ems of its own font size.
 *
 * Measured, not assumed: Plus Jakarta Sans with `tabular-nums` sets every digit at exactly 0.60em at
 * weights 400-600, and the group and decimal separators (0.27-0.35em) and the hyphen-minus Intl uses
 * (0.50-0.57em) are all narrower — so for what `fmt.value` produces, the character count times this is
 * an upper bound on the width, reached only by a figure that is all digits. It is NOT a bound for
 * letters or symbols (a currency code's "D" is 0.74em, the "−" sign 0.64em), which is why only the
 * bare headline figures are given `fit`.
 */
const MONEY_FIT_EM_PER_CHAR = 0.6;

interface MoneyFigureProps {
  // The formatted figure — `fmt.value(...)` / `fmt.amount(...)`, plus any sign or code shown with it.
  children: ReactNode;
  className?: string;
  // Shrink below the inherited size when the figure is wider than its container. Needs an ancestor
  // that is a size container (`@container`); `MetricCard` is one.
  fit?: boolean;
  // Room inside that container the figure must leave free for a sibling (a CSS length).
  fitReserve?: string;
}

/*
 * Every standalone money figure the app renders goes through this, and two things follow from that.
 *
 * `data-money` marks it, so the e2e overflow sweep can find every figure on a page without knowing any
 * page's markup — a figure clipped by its card reads as a DIFFERENT number ("4,419,879.7" for
 * 4,419,879.70), with no ellipsis to say anything is missing. And `whitespace-nowrap` keeps it whole: a
 * figure never breaks across lines, since the two halves read as two amounts.
 *
 * `fit` is the guarantee for figures that have no room to grow into, the metric cards: the size steps
 * down just enough that the figure fits the container (`100cqi`, less any `fitReserve`), and `1em` caps it at whatever size the
 * parent sets, so a figure that already fits renders exactly as designed. The rule it encodes is the
 * one this component exists for: when something has to give, it is the type size, never a digit.
 */
export function MoneyFigure({ children, className, fit = false, fitReserve }: MoneyFigureProps) {
  const chars = Children.toArray(children)
    .filter((child) => typeof child === 'string' || typeof child === 'number')
    .join('').length;
  const room = fitReserve ? `(100cqi - ${fitReserve})` : '100cqi';
  const style: CSSProperties | undefined =
    fit && chars > 0
      ? { fontSize: `min(1em, calc(${room} / (${chars} * ${MONEY_FIT_EM_PER_CHAR})))` }
      : undefined;

  return (
    <span data-money="" className={cn('whitespace-nowrap tabular-nums', className)} style={style}>
      {children}
    </span>
  );
}
