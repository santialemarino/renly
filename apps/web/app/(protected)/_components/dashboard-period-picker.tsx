'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { format } from 'date-fns';
import { CalendarDays } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useLocale, useTranslations } from 'next-intl';
import type { DateRange } from 'react-day-picker';

import { Button, Calendar, Popover, PopoverContent, PopoverTrigger } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PERIOD_PRESETS, type PeriodPreset } from '@/lib/constants/period-presets';
import { getDateFnsLocale } from '@/lib/i18n/locales';
import { formatPresetLabel } from '@/lib/utils/period-presets';

const DATE_FORMAT = 'MMM d, yyyy';

interface DashboardPeriodPickerProps {
  routePath: string;
  translationNamespace: 'dashboard' | 'financeDashboard' | 'investorDashboard';
  presets?: PeriodPreset[];
  className?: string;
}

// Period preset pills + custom date range picker. Shared by finance and investor dashboards.
export function DashboardPeriodPicker({
  routePath,
  translationNamespace,
  presets = PERIOD_PRESETS,
  className,
}: DashboardPeriodPickerProps) {
  const locale = useLocale();
  const t = useTranslations(translationNamespace);
  const tCommon = useTranslations('common');
  const router = useRouter();
  const searchParams = useSearchParams();
  const dateFnsLocale = getDateFnsLocale(locale);

  const currentPeriod = searchParams.get('period');
  const currentStartDate = searchParams.get('start_date');
  const currentEndDate = searchParams.get('end_date');
  const isCustom = !!(currentStartDate && currentEndDate) && !currentPeriod;
  const activePreset = currentPeriod ?? (isCustom ? null : 'all');

  const [calendarOpen, setCalendarOpen] = useState(false);
  // Parse as local midnight — a bare YYYY-MM-DD parses as UTC midnight and renders the
  // prior day in negative-offset zones.
  const [dateRange, setDateRange] = useState<DateRange | undefined>(
    currentStartDate && currentEndDate
      ? {
          from: new Date(`${currentStartDate}T00:00:00`),
          to: new Date(`${currentEndDate}T00:00:00`),
        }
      : undefined,
  );

  function navigate(params: Record<string, string | null>) {
    const qs = new URLSearchParams(searchParams.toString());
    Object.entries(params).forEach(([key, val]) => {
      if (val === null) qs.delete(key);
      else qs.set(key, val);
    });
    router.push(`${routePath}?${qs.toString()}`, { scroll: false });
  }

  function handlePresetChange(value: string) {
    if (!value) return;
    if (value === 'all') {
      navigate({ period: null, start_date: null, end_date: null });
    } else {
      navigate({ period: value, start_date: null, end_date: null });
    }
  }

  function handleCustomApply() {
    if (dateRange?.from && dateRange?.to) {
      const startDate = format(dateRange.from, 'yyyy-MM-dd');
      const endDate = format(dateRange.to, 'yyyy-MM-dd');
      navigate({ period: null, start_date: startDate, end_date: endDate });
      setCalendarOpen(false);
    }
  }

  return (
    <LayoutGroup>
      <div className={cn('flex flex-wrap items-center gap-x-2 gap-y-2', className)}>
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="flex-1">
          <PillToggleGroup
            items={presets.map((preset) => ({
              value: preset.code,
              label: formatPresetLabel(preset.code, {
                ytd: t('period.ytd'),
                all: t('period.all'),
                monthSuffix: tCommon('period.monthSuffix'),
                yearSuffix: tCommon('period.yearSuffix'),
              }),
            }))}
            value={activePreset ?? ''}
            onValueChange={handlePresetChange}
            itemClassName="flex-1"
            className="w-full"
          />
        </motion.div>

        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="flex-1">
          <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
            <PopoverTrigger asChild>
              <Button
                variant={isCustom ? 'default' : 'outline'}
                blue={isCustom}
                className="h-9 w-full gap-x-1.5 px-3 text-paragraph-sm"
              >
                <CalendarDays className="size-4" />
                {isCustom && dateRange?.from && dateRange?.to
                  ? `${format(dateRange.from, DATE_FORMAT, { locale: dateFnsLocale })} – ${format(dateRange.to, DATE_FORMAT, { locale: dateFnsLocale })}`
                  : t('period.custom')}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar
                blue
                mode="range"
                selected={dateRange}
                onSelect={setDateRange}
                numberOfMonths={2}
                locale={dateFnsLocale}
              />
              <div className="flex items-center justify-end gap-x-2 p-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDateRange(undefined);
                    setCalendarOpen(false);
                  }}
                >
                  {t('period.cancel')}
                </Button>
                <Button
                  blue
                  size="sm"
                  disabled={!dateRange?.from || !dateRange?.to}
                  onClick={handleCustomApply}
                >
                  {t('period.apply')}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </motion.div>
      </div>
    </LayoutGroup>
  );
}
