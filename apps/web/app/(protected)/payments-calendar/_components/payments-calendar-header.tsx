'use client';

import { useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { useFormatters } from '@/lib/i18n/formatters';
import { currentYearMonth } from '@/lib/utils/dates';

interface PaymentsCalendarHeaderProps {
  year: number;
  month: number;
  timeZone?: string;
}

export function PaymentsCalendarHeader({ year, month, timeZone }: PaymentsCalendarHeaderProps) {
  const fmt = useFormatters();
  const t = useTranslations('paymentsCalendar');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  // Locale-aware month name (e.g. "May" / "mayo").
  const monthLabel = fmt.monthLong(year, month);

  function navigate(targetYear: number, targetMonth: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('year', String(targetYear));
    params.set('month', String(targetMonth));
    startTransition(() => router.push(`${ROUTES.paymentsCalendar}?${params.toString()}`));
  }

  function handlePrevious() {
    const prevMonth = month === 1 ? 12 : month - 1;
    const prevYear = month === 1 ? year - 1 : year;
    navigate(prevYear, prevMonth);
  }

  function handleNext() {
    const nextMonth = month === 12 ? 1 : month + 1;
    const nextYear = month === 12 ? year + 1 : year;
    navigate(nextYear, nextMonth);
  }

  function handleToday() {
    const { year: nowYear, month: nowMonth } = currentYearMonth(timeZone);
    navigate(nowYear, nowMonth);
  }

  return (
    <div className="flex items-center justify-between gap-x-3 pb-1">
      <div className="text-heading-4 tabular-nums">
        {t('monthLabel', { month: monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1), year })}
      </div>
      <div className="flex items-center gap-x-2">
        <Button
          variant="outline"
          size="icon"
          onClick={handlePrevious}
          aria-label={t('navigation.previous')}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="outline" onClick={handleToday}>
          {t('navigation.today')}
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={handleNext}
          aria-label={t('navigation.next')}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
