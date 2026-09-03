'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, CircleDollarSign, Lock, Minus, Plus, Table2 } from 'lucide-react';
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
import { SnapshotFormDialog } from '@/app/(protected)/snapshots/_components/snapshot-form-dialog';
import { TRANSACTION_TYPES_OUTGOING } from '@/app/(protected)/snapshots/snapshots-form-schema';
import { EmptyState } from '@/components/empty-state';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortIcon } from '@/components/sort-icon';
import { TableSectionRow } from '@/components/table-section-row';
import { ROUTES } from '@/config/routes';
import type { SnapshotGridCell, SnapshotGridResponse, SnapshotGridRow } from '@/lib/api/snapshots';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { useFormatters } from '@/lib/i18n/formatters';
import { bySectionPot, sectionedRows } from '@/lib/list-scope';

interface CellContentProps {
  cell: SnapshotGridCell;
}

function CellContent({ cell }: CellContentProps) {
  const fmt = useFormatters();
  return (
    <div className="flex items-center justify-center gap-x-1.5">
      {cell.quantity !== null ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="text-paragraph-sm tabular-nums cursor-default">
              {fmt.value(cell.value)}
            </span>
          </TooltipTrigger>
          <TooltipContent>{cell.quantity} shares</TooltipContent>
        </Tooltip>
      ) : (
        <span className="text-paragraph-sm tabular-nums">{fmt.value(cell.value)}</span>
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
          {fmt.signedPct(cell.periodReturnPct)}
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
              {fmt.value(cell.transaction.amount)}
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
  const fmt = useFormatters();
  const t = useTranslations('snapshots');
  const tCommon = useTranslations('common');
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

  /*
   * Cell lookup per row: COLUMN → the latest-dated cell in it.
   *
   * The column key comes from the API rather than being derived here, which is the point of moving
   * it: the pot page's value series is measured on the same period rule, and a second copy in the
   * browser would have to agree with it about which week a Wednesday belongs to. Which cell WINS a
   * column stays here, because it is a rendering choice — the other cells are still in `cells`, so
   * the form knows every date that is taken.
   */
  const cellMaps = useMemo(
    () =>
      grid.rows.map((row) => {
        const map = new Map<string, SnapshotGridCell>();
        for (const cell of row.cells) {
          const existing = map.get(cell.column);
          if (!existing || cell.date > existing.date) map.set(cell.column, cell);
        }
        return map;
      }),
    [grid.rows],
  );

  const rendered = sectionedRows(grid.rows, grid.sections, {
    rowKey: (row) => String(row.investmentId),
    scopeKey: (row) => row.potId,
    sectionKey: bySectionPot,
  });
  // Write access is a property of the section: only a member the pot granted it to may value a shared
  // holding, and a row with no section is the caller's own.
  const writableByPot = new Map(grid.sections.map((section) => [section.potId, section.canWrite]));
  // Every column plus the two sticky ones, for a section header that spans the whole grid.
  const columnCount = grid.columns.length + 2;

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
              {grid.columns.map((column) => (
                <TableHead
                  key={column}
                  className="min-w-[140px] text-center text-paragraph-xs bg-background transition-colors group-hover:bg-muted/50"
                >
                  {/*
                   * A monthly column IS its month. A weekly column is the day its week closed, WITH
                   * the month: the weekday would be "Sunday" on every column, and a bare day number
                   * leaves July's 5th and August's 2nd reading identically.
                   */}
                  {grid.interval === 'weekly' ? fmt.dayMonth(column) : fmt.month(column)}
                </TableHead>
              ))}
              <TableHead className="sticky right-0 z-10 min-w-[70px] bg-background text-center">
                {t('grid.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rendered.map((entry) => {
              if (entry.kind === 'header') {
                return (
                  <TableSectionRow
                    key={entry.key}
                    section={entry.section}
                    colSpan={columnCount}
                    countLabel={t('grid.sectionCount', { count: entry.section.count })}
                  />
                );
              }
              const row = entry.row;
              const rowIdx = grid.rows.indexOf(row);
              const canWrite = writableByPot.get(row.potId) ?? true;
              return (
                <TableRow key={entry.key} className="group">
                  <TableCell className="sticky left-0 z-10 bg-background">
                    <div className="flex flex-col">
                      <span className="text-paragraph-sm-medium truncate max-w-[200px]">
                        {row.name}
                      </span>
                      <span className="text-paragraph-xs text-muted-foreground">
                        {row.baseCurrency}
                      </span>
                      {/*
                       * §8.2's cadence-driven freshness indicator, and it is per ROW because
                       * lateness is a fact about this holding: two holdings in one pot can be one
                       * current and one months old. Only a shared row has a cadence to be late
                       * against — a private holding declares no rhythm at all.
                       */}
                      {row.isOverdue && row.cadence !== null && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="w-fit text-paragraph-mini-medium text-amber-600 cursor-default">
                              {t('grid.overdue')}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            {row.cells.length === 0
                              ? t('grid.neverValued', {
                                  cadence: tCommon(`cadence.${row.cadence}`).toLowerCase(),
                                })
                              : t('grid.overdueHint', {
                                  date: fmt.date(row.cells[row.cells.length - 1]!.date),
                                  cadence: tCommon(`cadence.${row.cadence}`).toLowerCase(),
                                })}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </TableCell>
                  {grid.columns.map((column) => {
                    const cell = cellMaps[rowIdx]?.get(column);
                    return (
                      <TableCell
                        key={column}
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
                    {/*
                     * Valuing a shared holding is what keeps its pot valued at all, so the grid
                     * offers it — but only to a member the pot granted write access to. The
                     * indicator rather than a disabled button: a Radix tooltip never fires on a
                     * disabled trigger, so the explanation would never render.
                     */}
                    {!canWrite ? (
                      <RowLockedIndicator
                        icon={Lock}
                        tooltip={t('grid.lockedAdd')}
                        ariaLabel="Managed by the pot"
                      />
                    ) : (
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
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
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
