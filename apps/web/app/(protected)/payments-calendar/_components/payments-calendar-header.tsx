'use client';

import { useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { getLocaleTag } from '@/lib/utils/locale';

interface PaymentsCalendarHeaderProps {
  year: number;
  month: number;
}

export function PaymentsCalendarHeader({ year, month }: PaymentsCalendarHeaderProps) {
  const t = useTranslations('paymentsCalendar');
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

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
    const now = new Date();
    navigate(now.getFullYear(), now.getMonth() + 1);
  }

  // Locale-aware month name (e.g. "May" / "mayo").
  const monthLabel = new Date(year, month - 1, 1).toLocaleDateString(getLocaleTag(locale), {
    month: 'long',
  });

  return (
    <div className="flex items-center justify-between gap-x-3 pb-1">
      <div className="text-heading-lg font-semibold tabular-nums">
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
