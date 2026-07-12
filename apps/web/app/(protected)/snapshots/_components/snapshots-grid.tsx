'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, CircleDollarSign, Minus, Plus, Table2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { SnapshotFormDialog } from '@/app/(protected)/snapshots/_components/snapshot-form-dialog';
import { TRANSACTION_TYPES_OUTGOING } from '@/app/(protected)/snapshots/snapshots-form-schema';
import { EmptyState } from '@/components/empty-state';
import { SortIcon } from '@/components/sort-icon';
import { ROUTES } from '@/config/routes';
import type { SnapshotGridCell, SnapshotGridResponse, SnapshotGridRow } from '@/lib/api/snapshots';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { formatMonth, formatSignedPct, formatValue } from '@/lib/utils/format';

// Extracts "YYYY-MM" from a date string like "2025-01-31".
function toYearMonth(dateStr: string): string {
  return dateStr.slice(0, 7);
}

// Generates all "YYYY-MM" keys between global min and max snapshot dates.
function generateAllYearMonths(dates: string[]): string[] {
  if (dates.length === 0) return [];
  const yms = dates.map(toYearMonth);
  const sorted = [...new Set(yms)].sort();
  const min = sorted[0]!;
  const max = sorted[sorted.length - 1]!;

  const result: string[] = [];
  const [minY, minM] = min.split('-').map(Number) as [number, number];
  const [maxY, maxM] = max.split('-').map(Number) as [number, number];
  let y = minY;
  let m = minM;

  while (y < maxY || (y === maxY && m <= maxM)) {
    result.push(`${y}-${String(m).padStart(2, '0')}`);
    m++;
    if (m > 12) {
      m = 1;
      y++;
    }
  }

  return result;
}

interface CellContentProps {
  cell: SnapshotGridCell;
}

function CellContent({ cell }: CellContentProps) {
  const locale = useLocale();
  return (
    <div className="flex items-center justify-center gap-x-1.5">
      {cell.quantity !== null ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="text-paragraph-sm tabular-nums cursor-default">
              {formatValue(cell.value, { locale })}
            </span>
          </TooltipTrigger>
          <TooltipContent>{cell.quantity} shares</TooltipContent>
        </Tooltip>
      ) : (
        <span className="text-paragraph-sm tabular-nums">
          {formatValue(cell.value, { locale })}
        </span>
      )}

      {cell.periodReturnPct !== null && (
        <span
          className={`flex items-center gap-x-0.5 text-paragraph-xs tabular-nums ${
            cell.periodReturnPct > 0
              ? 'text-emerald-600'
              : cell.periodReturnPct < 0
                ? 'text-red-500'
                : 'text-muted-foreground'
          }`}
        >
          {cell.periodReturnPct > 0 ? (
            <ArrowUp className="size-3" />
          ) : cell.periodReturnPct < 0 ? (
            <ArrowDown className="size-3" />
          ) : (
            <Minus className="size-3" />
          )}
          {formatSignedPct(cell.periodReturnPct, locale)}
        </span>
      )}

      {cell.hasTransaction && cell.transaction && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex items-center gap-x-0.5 text-paragraph-xs text-blue-500 shrink-0">
              <CircleDollarSign className="size-3.5" />
              {(TRANSACTION_TYPES_OUTGOING as readonly string[]).includes(cell.transaction.type)
                ? '-'
                : '+'}
              {formatValue(cell.transaction.amount, { locale })}
            </span>
          </TooltipTrigger>
          <TooltipContent>{cell.transaction.type}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

interface SnapshotsGridProps {
  grid: SnapshotGridResponse;
  firstRun?: boolean;
}

export function SnapshotsGrid({ grid, firstRun }: SnapshotsGridProps) {
  const locale = useLocale();
  const t = useTranslations('snapshots');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.snapshots);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SnapshotGridRow | null>(null);
  const [selectedCell, setSelectedCell] = useState<SnapshotGridCell | undefined>(undefined);

  // Sorting (server-side via URL params).
  const sortOrder = (searchParams.get('sort_order') as 'asc' | 'desc' | null) ?? 'asc';
  const sortBy = searchParams.get('sort_by');
  const isSortActive = sortBy === 'name';

  function handleSortChange() {
    if (!isSortActive) {
      navigate({ sort_by: 'name', sort_order: 'asc' });
    } else if (sortOrder === 'asc') {
      navigate({ sort_by: 'name', sort_order: 'desc' });
    } else {
      navigate({ sort_by: null, sort_order: null });
    }
  }

  // Generate all year-month keys between global min and max (fill gaps).
  const allYearMonths = useMemo(() => generateAllYearMonths(grid.months), [grid.months]);

  // Build cell lookup per row: year-month → cell.
  // Build cell lookup per row: year-month → latest-dated cell in that month.
  const cellMaps = useMemo(
    () =>
      grid.rows.map((row) => {
        const map = new Map<string, SnapshotGridCell>();
        for (const cell of row.cells) {
          const key = toYearMonth(cell.date);
          const existing = map.get(key);
          if (!existing || cell.date > existing.date) map.set(key, cell);
        }
        return map;
      }),
    [grid.rows],
  );

  function handleCellClick(row: SnapshotGridRow, cell: SnapshotGridCell, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedRow(row);
    setSelectedCell(cell);
    setDialogOpen(true);
  }

  function handleAddClick(row: SnapshotGridRow, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedRow(row);
    setSelectedCell(undefined);
    setDialogOpen(true);
  }

  if (grid.rows.length === 0) {
    if (firstRun) {
      return (
        <EmptyState
          icon={Table2}
          title={t('grid.emptyTitle')}
          description={t('grid.emptyDescription')}
        />
      );
    }
    return <p className="text-paragraph-sm text-muted-foreground">{t('grid.empty')}</p>;
  }

  return (
    <>
      <div className="overflow-auto rounded-lg border border-border-3 shadow-xs">
        <Table>
          <TableHeader>
            <TableRow className="group">
              <TableHead className="sticky left-0 z-10 min-w-[120px] bg-background">
                <button
                  type="button"
                  onClick={handleSortChange}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('grid.investment')}
                  <SortIcon active={isSortActive} order={sortOrder} />
                </button>
              </TableHead>
              {allYearMonths.map((month) => (
                <TableHead
                  key={month}
                  className="min-w-[140px] text-center text-paragraph-xs bg-background transition-colors group-hover:bg-muted/50"
                >
                  {formatMonth(month + '-01', locale)}
                </TableHead>
              ))}
              <TableHead className="sticky right-0 z-10 min-w-[70px] bg-background text-center">
                {t('grid.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {grid.rows.map((row, rowIdx) => (
              <TableRow key={row.investmentId} className="group">
                <TableCell className="sticky left-0 z-10 bg-background">
                  <div className="flex flex-col">
                    <span className="text-paragraph-sm-medium truncate max-w-[200px]">
                      {row.name}
                    </span>
                    <span className="text-paragraph-xs text-muted-foreground">
                      {row.baseCurrency}
                    </span>
                  </div>
                </TableCell>
                {allYearMonths.map((month) => {
                  const cell = cellMaps[rowIdx]?.get(month);
                  return (
                    <TableCell
                      key={month}
                      className={`text-center bg-background transition-colors group-hover:bg-muted/50 ${cell ? 'cursor-pointer' : ''}`}
                      onClick={cell ? (e) => handleCellClick(row, cell, e) : undefined}
                    >
                      {cell ? (
                        <CellContent cell={cell} />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  );
                })}
                <TableCell className="sticky right-0 z-10 bg-background text-center">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={(e) => handleAddClick(row, e)}
                        aria-label="Add snapshot"
                      >
                        <Plus className="size-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>{t('grid.addSnapshot')}</TooltipContent>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {selectedRow && (
        <SnapshotFormDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          investmentId={selectedRow.investmentId}
          investmentName={selectedRow.name}
          baseCurrency={selectedRow.baseCurrency}
          ticker={selectedRow.ticker}
          category={selectedRow.category}
          cedearRatio={selectedRow.cedearRatio}
          existingDates={selectedRow.cells.map((c) => c.date)}
          cell={selectedCell}
          onSuccess={() => router.refresh()}
        />
      )}
    </>
  );
}
