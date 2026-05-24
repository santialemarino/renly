import { getLocale, getTranslations } from 'next-intl/server';

import { Badge } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { PaymentsCalendarItem } from '@/lib/api/payments-calendar';
import { formatAmount } from '@/lib/utils/currency';

interface PaymentsCalendarListProps {
  items: PaymentsCalendarItem[];
  year: number;
  month: number;
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

export async function PaymentsCalendarList({ items, year, month }: PaymentsCalendarListProps) {
  const t = await getTranslations('paymentsCalendar');
  const locale = await getLocale();

  if (items.length === 0) {
    const monthName = new Date(year, month - 1, 1).toLocaleDateString(locale, { month: 'long' });
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

  const today = new Date();
  const todayIso =
    today.getFullYear() === year && today.getMonth() + 1 === month
      ? today.toISOString().slice(0, 10)
      : null;

  const sortedDates = Array.from(groups.keys()).sort();

  return (
    <div className="flex flex-col gap-y-4">
      {sortedDates.map((dateStr) => {
        const dayItems = groups.get(dateStr) ?? [];
        const isToday = dateStr === todayIso;
        const day = new Date(`${dateStr}T00:00:00`);
        const dayLabel = day.toLocaleDateString(locale, { weekday: 'long', day: 'numeric' });
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
                return (
                  <div
                    key={`${item.type}-${item.sourceId}-${idx}`}
                    className="flex items-center justify-between gap-x-3 rounded-md border border-border px-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-x-3">
                      <Badge variant={TYPE_VARIANT[item.type]} className="shrink-0">
                        {t(`types.${item.type}`)}
                      </Badge>
                      <div className="flex min-w-0 flex-col">
                        <div className="text-paragraph-sm-medium truncate">{item.name}</div>
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
                    <div className="flex items-baseline gap-x-1.5 text-paragraph-sm tabular-nums">
                      <span>{formatAmount(displayAmount)}</span>
                      {showOriginalCurrency && (
                        <span className="text-paragraph-xs text-muted-foreground">
                          {item.currency}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
