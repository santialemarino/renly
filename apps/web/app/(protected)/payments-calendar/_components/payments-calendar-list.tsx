import { getTranslations } from 'next-intl/server';

import { Badge } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { LinkedExpenseEditTrigger } from '@/app/(protected)/payments-calendar/_components/linked-expense-edit-trigger';
import { MoneyFigure } from '@/components/money-figure';
import { TruncatingTooltip } from '@/components/truncating-tooltip';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { PaymentsCalendarItem } from '@/lib/api/payments-calendar';
import type { Subscription } from '@/lib/api/subscriptions';
import { getFormatters } from '@/lib/i18n/formatters-server';
import { todayInTimezone } from '@/lib/utils/dates';

interface PaymentsCalendarListProps {
  items: PaymentsCalendarItem[];
  year: number;
  month: number;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  accounts?: Account[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  activeCurrency?: string;
  timeZone?: string;
}

// Variant colour per entry type — keeps the timeline scannable.
const TYPE_VARIANT: Record<
  PaymentsCalendarItem['type'],
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  subscription: 'secondary',
  installment: 'outline',
  obligation: 'default',
  card_due: 'destructive',
};

export async function PaymentsCalendarList({
  items,
  year,
  month,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  activeCurrency,
  timeZone,
}: PaymentsCalendarListProps) {
  const fmt = await getFormatters();
  const t = await getTranslations('paymentsCalendar');

  if (items.length === 0) {
    const monthName = fmt.monthLong(year, month);
    return (
      <div className="rounded-lg border border-border py-10 text-center text-muted-foreground">
        {t('empty', { month: monthName.charAt(0).toUpperCase() + monthName.slice(1) })}
      </div>
    );
  }

  // Group items by date for the timeline.
  const groups = new Map<string, PaymentsCalendarItem[]>();
  for (const item of items) {
    const bucket = groups.get(item.date) ?? [];
    bucket.push(item);
    groups.set(item.date, bucket);
  }

  // Highlight "today" only when viewing the current month — both resolved in the user's tz.
  const today = todayInTimezone(timeZone);
  const todayIso =
    Number(today.slice(0, 4)) === year && Number(today.slice(5, 7)) === month ? today : null;

  const sortedDates = Array.from(groups.keys()).sort();

  return (
    <div className="flex flex-col gap-y-4">
      {sortedDates.map((dateStr) => {
        const dayItems = groups.get(dateStr) ?? [];
        const isToday = dateStr === todayIso;
        const dayLabel = fmt.weekdayDay(dateStr);
        return (
          <div key={dateStr} className="flex flex-col gap-y-2">
            <div
              className={cn(
                'text-paragraph-sm-medium',
                isToday ? 'text-blue-800' : 'text-muted-foreground',
              )}
            >
              {dayLabel.charAt(0).toUpperCase() + dayLabel.slice(1)}
            </div>
            <div className="flex flex-col gap-y-1.5">
              {dayItems.map((item, idx) => {
                const displayAmount = item.convertedAmount ?? item.amount;
                const showOriginalCurrency = !item.convertedAmount;
                const rowContent = (
                  <div
                    className={cn(
                      'flex items-center justify-between gap-x-3 rounded-md border border-border px-3 py-2',
                      item.isPaid && 'hover:bg-muted/40 transition-colors',
                    )}
                  >
                    {/*
                     * The name wins: it keeps at least `basis-40` of the row, and when the badge
                     * leaves it less ("Vencimiento de tarjeta" is ~2.75x "Card due") it wraps onto its
                     * own line under the badge instead of being squeezed. Past that it truncates,
                     * with the full name in a tooltip.
                     */}
                    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                      {item.isPaid ? (
                        <Badge
                          variant="default"
                          className="shrink-0 bg-emerald-100 [a&]:hover:bg-emerald-100 text-emerald-800"
                        >
                          {t('types.paid')}
                        </Badge>
                      ) : (
                        <Badge variant={TYPE_VARIANT[item.type]} className="shrink-0">
                          {t(`types.${item.type}`)}
                        </Badge>
                      )}
                      <div className="flex min-w-0 flex-1 basis-40 flex-col">
                        <TruncatingTooltip text={item.name} className="text-paragraph-sm-medium" />
                        {item.type === 'installment' &&
                          item.cuotaIndex !== null &&
                          item.installmentsCount !== null && (
                            <div className="text-paragraph-xs text-muted-foreground">
                              {t('installment.progress', {
                                index: item.cuotaIndex,
                                total: item.installmentsCount,
                              })}
                            </div>
                          )}
                      </div>
                    </div>
                    <MoneyFigure className="flex items-baseline gap-x-1.5 text-paragraph-sm">
                      {fmt.amount(
                        displayAmount,
                        item.convertedAmount ? activeCurrency : item.currency,
                      )}
                      {showOriginalCurrency && (
                        <span className="text-paragraph-xs text-muted-foreground">
                          {item.currency}
                        </span>
                      )}
                    </MoneyFigure>
                  </div>
                );
                // Paid rows are clickable — open the linked expense's edit dialog inline
                // (no navigation). Non-paid rows stay static. Falls back to a non-clickable
                // row if linkedExpenseId is missing defensively.
                if (item.isPaid && item.linkedExpenseId !== null) {
                  return (
                    <LinkedExpenseEditTrigger
                      key={`${item.type}-${item.sourceId}-${idx}`}
                      linkedExpenseId={item.linkedExpenseId}
                      preferredCurrencies={preferredCurrencies}
                      supportedCurrencies={supportedCurrencies}
                      creditCards={creditCards}
                      accounts={accounts}
                      activeObligations={activeObligations}
                      activeSubscriptions={activeSubscriptions}
                      activeInstallments={activeInstallments}
                    >
                      {rowContent}
                    </LinkedExpenseEditTrigger>
                  );
                }
                return <div key={`${item.type}-${item.sourceId}-${idx}`}>{rowContent}</div>;
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
