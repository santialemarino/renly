'use client';

import { useMemo, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, ChevronsUpDown, CircleDollarSign, Minus, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

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
import { cn } from '@repo/ui/lib';
import { SnapshotFormDialog } from '@/app/(protected)/snapshots/_components/snapshot-form-dialog';
import { ROUTES } from '@/config/routes';
import type { SnapshotGridCell, SnapshotGridResponse, SnapshotGridRow } from '@/lib/api/snapshots';

// Extracts "YYYY-MM" from a date string like "2025-01-31".
function toYearMonth(dateStr: string): string {
  return dateStr.slice(0, 7);
}

// Formats a "YYYY-MM" string as a short month label (e.g. "Jan 25").
function formatMonth(ym: string): string {
  const d = new Date(ym + '-01T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

// Formats a number as a compact currency value (no decimals for integers, up to 2 for decimals).
function formatValue(value: number): string {
  const hasDecimals = value % 1 !== 0;
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: hasDecimals ? 2 : 0,
  }).format(value);
}

// Formats a decimal as a percentage string (e.g. 0.05 → "+5%", 0.052 → "+5.2%").
function formatPct(pct: number): string {
  const val = pct * 100;
  const hasDecimals = Math.round(val * 10) % 10 !== 0;
  const s = hasDecimals ? val.toFixed(1) : val.toFixed(0);
  return pct >= 0 ? `+${s}%` : `${s}%`;
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

function SortIcon({ active, order }: { active: boolean; order: 'asc' | 'desc' }) {
  const isAsc = active && order === 'asc';
  const isDesc = active && order === 'desc';
  return (
    <span className="grid shrink-0">
      <ChevronsUpDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-400 transition-all duration-200',
          active ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
        )}
      />
      <ArrowUp
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isAsc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
      <ArrowDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isDesc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
    </span>
  );
}

interface CellContentProps {
  cell: SnapshotGridCell;
}

function CellContent({ cell }: CellContentProps) {
  return (
    <div className="flex items-center justify-center gap-x-1.5">
      <span className="text-paragraph-sm tabular-nums">{formatValue(cell.value)}</span>

      {cell.periodReturnPct !== null && (
        <span
          className={`flex items-center gap-x-0.5 text-paragraph-mini tabular-nums ${
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
          {formatPct(cell.periodReturnPct)}
        </span>
      )}

      {cell.hasTransaction && cell.transaction && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex items-center gap-x-0.5 text-paragraph-mini text-blue-500 shrink-0">
              <CircleDollarSign className="size-3.5" />
              {cell.transaction.type === 'sell' || cell.transaction.type === 'withdrawal'
                ? '-'
                : '+'}
              {formatValue(cell.transaction.amount)}
            </span>
          </TooltipTrigger>
          <TooltipContent>{cell.transaction.type}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

// TODO: §11.4.1 — Read activeCurrency from Zustand store and pass it to the grid endpoint
// as a ?currency= param. When conversion is not available for the selected currency,
// fall back to original values (same as "Original" mode).

interface SnapshotsGridProps {
  grid: SnapshotGridResponse;
}

export function SnapshotsGrid({ grid }: SnapshotsGridProps) {
  const t = useTranslations('snapshots');
  const router = useRouter();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SnapshotGridRow | null>(null);
  const [selectedCell, setSelectedCell] = useState<SnapshotGridCell | undefined>(undefined);

  // Sorting (client-side — small dataset).
  const sortOrder = (searchParams.get('sort_order') as 'asc' | 'desc' | null) ?? 'asc';
  const sortBy = searchParams.get('sort_by');
  const isSortActive = sortBy === 'name';

  function handleSortChange() {
    const params = new URLSearchParams(searchParams.toString());
    if (!isSortActive) {
      params.set('sort_by', 'name');
      params.set('sort_order', 'asc');
    } else if (sortOrder === 'asc') {
      params.set('sort_order', 'desc');
    } else {
      params.delete('sort_by');
      params.delete('sort_order');
    }
    startTransition(() => router.push(`${ROUTES.snapshots}?${params.toString()}`));
  }

  // Generate all year-month keys between global min and max (fill gaps).
  const allYearMonths = useMemo(() => generateAllYearMonths(grid.months), [grid.months]);

  // Sort rows client-side.
  const sortedRows = useMemo(() => {
    if (!isSortActive) return grid.rows;
    const sorted = [...grid.rows].sort((a, b) => a.name.localeCompare(b.name));
    return sortOrder === 'desc' ? sorted.reverse() : sorted;
  }, [grid.rows, isSortActive, sortOrder]);

  // Build cell lookup per row: year-month → cell.
  const cellMaps = useMemo(
    () =>
      sortedRows.map((row) => {
        const map = new Map<string, SnapshotGridCell>();
        for (const cell of row.cells) map.set(toYearMonth(cell.date), cell);
        return map;
      }),
    [sortedRows],
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
    return <p className="text-paragraph-sm text-muted-foreground">{t('grid.empty')}</p>;
  }

  return (
    <>
      <div className="overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 z-10 min-w-[180px] bg-background">
                <button
                  type="button"
                  onClick={handleSortChange}
                  className="flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:animate-focus-bump"
                >
                  {t('grid.investment')}
                  <SortIcon active={isSortActive} order={sortOrder} />
                </button>
              </TableHead>
              {allYearMonths.map((month) => (
                <TableHead key={month} className="min-w-[140px] text-center text-paragraph-mini">
                  {formatMonth(month)}
                </TableHead>
              ))}
              <TableHead className="sticky right-0 z-10 w-[50px] bg-background text-center">
                {t('grid.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedRows.map((row, rowIdx) => (
              <TableRow key={row.investmentId}>
                <TableCell className="sticky left-0 z-10 bg-background">
                  <div className="flex flex-col">
                    <span className="text-paragraph-sm-medium truncate max-w-[200px]">
                      {row.name}
                    </span>
                    <span className="text-paragraph-mini text-muted-foreground">
                      {row.baseCurrency}
                    </span>
                  </div>
                </TableCell>
                {allYearMonths.map((month) => {
                  const cell = cellMaps[rowIdx]?.get(month);
                  return (
                    <TableCell
                      key={month}
                      className={`text-center ${cell ? 'cursor-pointer hover:bg-muted/50' : ''}`}
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
                        aria-label={t('grid.addSnapshot')}
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
          existingDates={selectedRow.cells.map((c) => c.date)}
          cell={selectedCell}
          onSuccess={() => router.refresh()}
        />
      )}
    </>
  );
}
