'use client';

import { cn } from '@repo/ui/lib';
import { useFormatters } from '@/lib/i18n/formatters';

interface SignedAmountCellProps {
  // Unsigned magnitude, as a decimal string. `outgoing` carries the direction.
  amount: string;
  currency: string;
  outgoing: boolean;
  // Optional second line beneath the amount (e.g. the other side of a cross-currency movement). The
  // CONTENT stays with each caller — the two surfaces word it differently on purpose — while the
  // typography lives here so it can't drift.
  subLine?: React.ReactNode;
}

/*
 * A movement's amount as an account sees it: an explicit sign, the magnitude, and the muted treatment
 * for money leaving. Shared by the transfers sub-table and the per-account ledger, which render the
 * same transfer rows — two copies of this styling would drift the moment either gained a variant.
 * The sign is prefixed rather than left to Intl so a positive movement reads "+" rather than bare.
 */
export function SignedAmountCell({ amount, currency, outgoing, subLine }: SignedAmountCellProps) {
  const fmt = useFormatters();

  return (
    <>
      <span
        className={cn(
          'text-paragraph-sm tabular-nums',
          outgoing ? 'text-muted-foreground' : 'text-foreground',
        )}
      >
        {outgoing ? '−' : '+'}
        {fmt.amount(amount, currency)}
      </span>
      {subLine && <span className="block text-paragraph-xs text-muted-foreground">{subLine}</span>}
    </>
  );
}
