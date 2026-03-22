'use client';

import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { InvestmentsSummaryResponse } from '@/lib/api/metrics';

// Formats a number as a compact currency value.
function formatValue(value: number): string {
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

// Formats a decimal ratio as a display percentage (e.g. 0.05 → "+5%").
function formatPct(pct: number): string {
  const val = pct * 100;
  const hasDecimals = Math.round(val * 10) % 10 !== 0;
  const s = hasDecimals ? val.toFixed(1) : val.toFixed(0);
  return pct >= 0 ? `+${s}%` : `${s}%`;
}

interface InvestmentsSummaryTableProps {
  summary: InvestmentsSummaryResponse;
}

export function InvestmentsSummaryTable({ summary }: InvestmentsSummaryTableProps) {
  const t = useTranslations('dashboard');

  const hasData = summary.items.length > 0;

  return (
    <Card className="flex-1">
      <CardHeader className="px-6">
        <CardTitle className="text-paragraph-sm text-muted-foreground">
          {t('investmentsTable.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-6 pb-6">
        {hasData ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('investmentsTable.name')}</TableHead>
                <TableHead className="text-right">{t('investmentsTable.value')}</TableHead>
                <TableHead className="text-right">{t('investmentsTable.invested')}</TableHead>
                <TableHead className="text-right">{t('investmentsTable.gain')}</TableHead>
                <TableHead className="text-right">{t('investmentsTable.monthChange')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.items.map((item) => {
                const isGainPositive = (item.absoluteGain ?? 0) >= 0;
                const isChangePositive = (item.monthChangePct ?? 0) >= 0;
                const isChangeZero = item.monthChangePct === null || item.monthChangePct === 0;

                return (
                  <TableRow key={item.investmentId}>
                    <TableCell className="text-paragraph-sm-medium">{item.name}</TableCell>
                    <TableCell className="text-right text-paragraph-sm tabular-nums">
                      {item.currentValue !== null ? formatValue(item.currentValue) : '—'}
                    </TableCell>
                    <TableCell className="text-right text-paragraph-sm tabular-nums">
                      {formatValue(item.investedCapital)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right text-paragraph-sm tabular-nums',
                        isGainPositive ? 'text-emerald-600' : 'text-red-500',
                      )}
                    >
                      {item.absoluteGain !== null ? formatValue(item.absoluteGain) : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div
                        className={cn(
                          'flex items-center justify-end gap-x-1 text-paragraph-sm tabular-nums',
                          isChangeZero
                            ? 'text-muted-foreground'
                            : isChangePositive
                              ? 'text-emerald-600'
                              : 'text-red-500',
                        )}
                      >
                        {item.monthChangePct !== null ? formatPct(item.monthChangePct) : '—'}
                        {!isChangeZero &&
                          (isChangePositive ? (
                            <ArrowUp className="size-3.5" />
                          ) : (
                            <ArrowDown className="size-3.5" />
                          ))}
                        {isChangeZero && item.monthChangePct !== null && (
                          <Minus className="size-3.5" />
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : (
          <div className="flex h-[200px] items-center justify-center">
            <p className="text-paragraph-sm text-muted-foreground">{t('noData')}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
