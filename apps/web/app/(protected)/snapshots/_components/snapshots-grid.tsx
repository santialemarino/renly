'use client';

import { useId, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, CircleDollarSign, Lock, Minus, Plus, Table2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
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
import {
  TRANSACTION_TYPES_OUTGOING,
  type TRANSACTION_TYPES,
} from '@/app/(protected)/snapshots/snapshots-form-schema';
import { EmptyState } from '@/components/empty-state';
import { MoneyFigure } from '@/components/money-figure';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortIcon } from '@/components/sort-icon';
import { TableSectionRow } from '@/components/table-section-row';
import { TruncatingTooltip } from '@/components/truncating-tooltip';
import { ROUTES } from '@/config/routes';
import type { SnapshotGridCell, SnapshotGridResponse, SnapshotGridRow } from '@/lib/api/snapshots';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { useFormatters } from '@/lib/i18n/formatters';
import { bySectionPot, sectionedRows } from '@/lib/list-scope';
import { moveInGrid, resolveGridPosition, type GridPosition } from '@/lib/utils/grid-navigation';

// A quantity is stored to six decimals (a fraction of a coin), and the hint shows all of them.
const QUANTITY_DECIMALS = 6;

// The focus ring of a cell that is itself the grid's stop; inset, so the scroll container never clips it.
const CELL_FOCUS =
  'outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring';

// A hint line as a sentence, so the lines read apart when a screen reader joins them into one description.
function sentence(line: string): string {
  return /[.!?]$/.test(line) ? line : `${line}.`;
}

// Whether the element holds focus that came from the keyboard, the only focus that opens a cell's hint.
function hasKeyboardFocus(el: HTMLElement | null): boolean {
  return el !== null && document.activeElement === el && el.matches(':focus-visible');
}

// The element in a cell that takes the grid's stop: the cell itself, or the one control inside it.
function stopIn(cell: HTMLTableCellElement | undefined): HTMLElement | null {
  if (!cell) return null;
  return cell.hasAttribute('tabindex') ? cell : cell.querySelector<HTMLElement>('[tabindex]');
}

/*
 * Scrolls a focused column cell out from under the two sticky columns.
 *
 * The browser scrolls a focused element into its scroll container's view, but the name and actions
 * columns are pinned over that view, so a narrow screen leaves the cell an arrow just moved to (and the
 * hint anchored to it) hidden behind them. The pinned edges are read off the header row, which carries
 * the same sticky cells as every other row.
 */
function revealBesideStickyColumns(cell: HTMLTableCellElement, header: HTMLTableRowElement) {
  const first = header.cells[0];
  const last = header.cells[header.cells.length - 1];
  const scroller = cell.closest<HTMLElement>('[data-slot="table-container"]');
  if (!first || !last || !scroller || cell.colSpan > 1) return;
  if (cell.cellIndex === 0 || cell.cellIndex === header.cells.length - 1) return;
  const box = cell.getBoundingClientRect();
  const from = first.getBoundingClientRect().right;
  const to = last.getBoundingClientRect().left;
  if (box.left < from) scroller.scrollLeft -= from - box.left;
  else if (box.right > to) scroller.scrollLeft += box.right - to;
}

interface HintedCellProps extends React.ComponentProps<typeof TableCell> {
  // What a pointer user reads in the cell's tooltips, one line each; empty for a cell with none.
  hint: string[];
  side?: 'top' | 'bottom';
}

/*
 * A grid cell that is its own stop, and says on keyboard focus what a pointer user reads on hover.
 *
 * The pieces inside a cell keep their own hover tooltips, but they are no longer stops: the grid is one,
 * and the arrows move between cells. So the cell gathers those tooltips into one, opened only by a
 * KEYBOARD focus (a hover or a click would stack it on a piece's own), and points `aria-describedby` at
 * the same lines, so a screen reader announces them with the cell. The description is always in the
 * DOM rather than borrowed from the tooltip, which exists only while open and would race the focus.
 */
function HintedCell({ hint, side = 'top', children, ...cellProps }: HintedCellProps) {
  const descriptionId = useId();
  const ref = useRef<HTMLTableCellElement>(null);
  const [open, setOpen] = useState(false);
  // Whether Escape dismissed the hint, which is the one close that holds while the cell keeps focus.
  const dismissed = useRef(false);
  const hinted = hint.length > 0;
  const cell = (
    <TableCell
      ref={ref}
      role="gridcell"
      aria-describedby={hinted ? descriptionId : undefined}
      {...cellProps}
    >
      {children}
      {hinted && (
        <span id={descriptionId} hidden>
          {hint.map(sentence).join(' ')}
        </span>
      )}
    </TableCell>
  );
  if (!hinted) return cell;

  /*
   * Opens only on keyboard focus, and closes when focus leaves or Escape dismisses it. Radix also
   * closes a tooltip whenever anything around its trigger scrolls, and moving to a cell scrolls the grid
   * (the browser's own reveal, or the one past the sticky columns), so that close — and a pointer
   * leaving a focused cell — is ignored while the cell still holds focus.
   */
  function handleOpenChange(next: boolean) {
    if (next) {
      dismissed.current = false;
      setOpen(hasKeyboardFocus(ref.current));
    } else if (dismissed.current || document.activeElement !== ref.current) {
      setOpen(false);
    }
  }

  return (
    <Tooltip open={open} onOpenChange={handleOpenChange}>
      <TooltipTrigger asChild>{cell}</TooltipTrigger>
      <TooltipContent
        side={side}
        sideOffset={8}
        onEscapeKeyDown={() => {
          dismissed.current = true;
        }}
      >
        {hint.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </TooltipContent>
    </Tooltip>
  );
}

interface CellContentProps {
  cell: SnapshotGridCell;
  // The holding's own currency, which its period return is measured in.
  baseCurrency: string;
  // The currency the cell's VALUES are shown in; null when they are shown in the base currency.
  displayCurrency: string | null;
  // What the tooltips say, shared with the cell's keyboard hint.
  hint: CellHint;
}

/*
 * A period return is measured in the holding's OWN currency, not the display currency its value is
 * converted to: a peso holding can return +25% while its dollar value is flat. So the return names
 * its currency whenever the figure beside it is in another one, and its tooltip always says which.
 *
 * The tooltips here are for a pointer. None of their triggers is a stop: the CELL is the grid's stop,
 * and it carries the same lines to the keyboard (`useCellHint`, read through `HintedCell`).
 */
function CellContent({ cell, baseCurrency, displayCurrency, hint }: CellContentProps) {
  const fmt = useFormatters();
  const returnInOtherCurrency = displayCurrency !== null && displayCurrency !== baseCurrency;
  return (
    <div className="flex items-center justify-center gap-x-1.5">
      {cell.quantity !== null ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="text-paragraph-sm tabular-nums cursor-default">
              <MoneyFigure>{fmt.value(cell.value)}</MoneyFigure>
            </span>
          </TooltipTrigger>
          <TooltipContent>{hint.shares}</TooltipContent>
        </Tooltip>
      ) : (
        <MoneyFigure className="text-paragraph-sm">{fmt.value(cell.value)}</MoneyFigure>
      )}

      {cell.periodReturnPct !== null && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={`flex items-center gap-x-0.5 text-paragraph-xs tabular-nums cursor-default ${
                cell.periodReturnPct > 0
                  ? 'text-emerald-700'
                  : cell.periodReturnPct < 0
                    ? 'text-red-600'
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
              {/* One inline run, so the space before the code is real text: as two flex items the
                  gap is only visual, and a screen reader reads "+25.00%ARS". */}
              <span>
                {fmt.signedPct(cell.periodReturnPct)}
                {returnInOtherCurrency && (
                  <>
                    {' '}
                    <span className="text-muted-foreground">{baseCurrency}</span>
                  </>
                )}
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent>{hint.periodReturn}</TooltipContent>
        </Tooltip>
      )}

      {cell.hasTransaction && cell.transaction && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex items-center gap-x-0.5 text-paragraph-xs text-blue-700 shrink-0 cursor-default">
              <CircleDollarSign className="size-3.5" />
              <MoneyFigure>
                {(TRANSACTION_TYPES_OUTGOING as readonly string[]).includes(cell.transaction.type)
                  ? '-'
                  : '+'}
                {fmt.value(cell.transaction.amount)}
              </MoneyFigure>
            </span>
          </TooltipTrigger>
          <TooltipContent>{hint.transaction}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

interface CellHint {
  shares: string | null;
  periodReturn: string | null;
  transaction: string | null;
}

// What a cell's tooltips say, once, so the pointer's tooltips and the keyboard's hint cannot drift apart.
function useCellHint(cell: SnapshotGridCell, baseCurrency: string): CellHint {
  const fmt = useFormatters();
  const t = useTranslations('snapshots');
  return {
    shares:
      cell.quantity !== null
        ? t('grid.shares', {
            count: cell.quantity,
            quantity: fmt.value(cell.quantity, { maxDecimals: QUANTITY_DECIMALS }),
          })
        : null,
    periodReturn:
      cell.periodReturnPct !== null ? t('grid.returnIn', { currency: baseCurrency }) : null,
    transaction:
      cell.hasTransaction && cell.transaction
        ? t(`form.transaction.types.${cell.transaction.type as (typeof TRANSACTION_TYPES)[number]}`)
        : null,
  };
}

interface ValueCellProps {
  row: SnapshotGridRow;
  cell: SnapshotGridCell;
  displayCurrency: string | null;
  tabIndex: number;
  onOpen: (row: SnapshotGridRow, cell: SnapshotGridCell) => void;
}

// A filled cell: its value, return and transaction, opened for editing by a click, Enter or Space.
function ValueCell({ row, cell, displayCurrency, tabIndex, onOpen }: ValueCellProps) {
  const hint = useCellHint(cell, row.baseCurrency);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTableCellElement>) {
    if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return;
    e.preventDefault();
    onOpen(row, cell);
  }

  return (
    <HintedCell
      hint={[hint.shares, hint.periodReturn, hint.transaction].filter(
        (line): line is string => line !== null,
      )}
      tabIndex={tabIndex}
      onClick={(e) => {
        e.stopPropagation();
        onOpen(row, cell);
      }}
      onKeyDown={handleKeyDown}
      className={`cursor-pointer text-center bg-background transition-colors group-hover:bg-muted/50 ${CELL_FOCUS}`}
    >
      <CellContent
        cell={cell}
        baseCurrency={row.baseCurrency}
        displayCurrency={displayCurrency}
        hint={hint}
      />
    </HintedCell>
  );
}

interface SnapshotsGridProps {
  grid: SnapshotGridResponse;
  // The display currency the values are converted to; null shows each holding in its own.
  currency: string | null;
  firstRun?: boolean;
}

export function SnapshotsGrid({ grid, currency, firstRun }: SnapshotsGridProps) {
  const fmt = useFormatters();
  const t = useTranslations('snapshots');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const searchParams = useSearchParams();
  const { navigate } = useSearchParamsNavigation(ROUTES.snapshots);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SnapshotGridRow | null>(null);
  const [selectedCell, setSelectedCell] = useState<SnapshotGridCell | undefined>(undefined);
  // The cell holding the grid's one stop, as row and column (row 0 is the header).
  const [active, setActive] = useState<GridPosition>({ row: 0, col: 0 });
  const gridRef = useRef<HTMLTableElement>(null);

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
      new Map(
        grid.rows.map((row) => {
          const map = new Map<string, SnapshotGridCell>();
          for (const cell of row.cells) {
            const existing = map.get(cell.column);
            if (!existing || cell.date > existing.date) map.set(cell.column, cell);
          }
          return [row.investmentId, map] as const;
        }),
      ),
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

  /*
   * The grid is ONE stop, and the arrows move between its cells (a roving tabindex, the WAI-ARIA grid
   * pattern). A cell is a stop of its own up to three times over otherwise, so tabbing past a year of
   * monthly columns took hundreds of presses. Rows are the table's own: the header, then one per
   * rendered entry, a section header being a single cell spanning the row.
   */
  const rowWidths = [
    columnCount,
    ...rendered.map((entry) => (entry.kind === 'header' ? 1 : columnCount)),
  ];
  const current = resolveGridPosition(active, rowWidths);
  const tabIndexAt = (row: number, col: number) =>
    row === current.row && col === current.col ? 0 : -1;

  function handleGridKeyDown(e: React.KeyboardEvent<HTMLTableElement>) {
    if (!(e.target instanceof HTMLElement) || e.altKey || e.shiftKey) return;
    const next = moveInGrid(e.key, e.ctrlKey || e.metaKey, active, rowWidths);
    if (next === null) return;
    e.preventDefault();
    setActive(next);
    const to = resolveGridPosition(next, rowWidths);
    stopIn(gridRef.current?.rows[to.row]?.cells[to.col])?.focus();
  }

  /*
   * A click or a returning dialog moves the stop to the cell that took focus, keeping the column the
   * keyboard is in when that cell is the one it already resolves to (a section header's single cell).
   * An updater, because an arrow key focuses the next cell before its own move has rendered.
   */
  function handleGridFocus(e: React.FocusEvent<HTMLTableElement>) {
    const cell = e.target.closest('td, th');
    const tr = cell?.parentElement;
    if (!(cell instanceof HTMLTableCellElement) || !(tr instanceof HTMLTableRowElement)) return;
    const focused = { row: tr.rowIndex, col: cell.cellIndex };
    const header = gridRef.current?.rows[0];
    if (header) revealBesideStickyColumns(cell, header);
    setActive((previous) => {
      const resolved = resolveGridPosition(previous, rowWidths);
      return resolved.row === focused.row && resolved.col === focused.col ? previous : focused;
    });
  }

  function openCell(row: SnapshotGridRow, cell: SnapshotGridCell) {
    setSelectedRow(row);
    setSelectedCell(cell);
    setDialogOpen(true);
  }

  function handleAddClick(row: SnapshotGridRow, e: React.MouseEvent<HTMLButtonElement>) {
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
        <Table
          ref={gridRef}
          label={t('title')}
          role="grid"
          onKeyDown={handleGridKeyDown}
          onFocus={handleGridFocus}
        >
          <TableHeader>
            <TableRow className="group">
              <TableHead className="sticky left-0 z-10 min-w-[120px] bg-background">
                <button
                  type="button"
                  tabIndex={tabIndexAt(0, 0)}
                  onClick={handleSortChange}
                  className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
                >
                  {t('grid.investment')}
                  <SortIcon active={isSortActive} order={sortOrder} />
                </button>
              </TableHead>
              {grid.columns.map((column, columnIndex) => (
                <TableHead
                  key={column}
                  tabIndex={tabIndexAt(0, columnIndex + 1)}
                  className={`min-w-[140px] text-center text-paragraph-xs bg-background transition-colors group-hover:bg-muted/50 ${CELL_FOCUS}`}
                >
                  {/*
                   * A monthly column IS its month. A weekly column is the day its week closed, WITH
                   * the month: the weekday would be "Sunday" on every column, and a bare day number
                   * leaves July's 5th and August's 2nd reading identically.
                   */}
                  {grid.interval === 'weekly' ? fmt.dayMonth(column) : fmt.month(column)}
                </TableHead>
              ))}
              <TableHead
                tabIndex={tabIndexAt(0, columnCount - 1)}
                className={`sticky right-0 z-10 min-w-[70px] bg-background text-center ${CELL_FOCUS}`}
              >
                {t('grid.actions')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rendered.map((entry, entryIndex) => {
              const rowIndex = entryIndex + 1;
              if (entry.kind === 'header') {
                return (
                  <TableSectionRow
                    key={entry.key}
                    section={entry.section}
                    colSpan={columnCount}
                    countLabel={t('grid.sectionCount', { count: entry.section.count })}
                    tabIndex={tabIndexAt(rowIndex, 0)}
                  />
                );
              }
              const row = entry.row;
              const canWrite = writableByPot.get(row.potId) ?? true;
              // The row's latest snapshot, which is what its freshness is measured against. `at(-1)`
              // rather than an index, because the section walk no longer hands out positions.
              const latest = row.cells.at(-1);
              const overdueHint =
                row.isOverdue && row.cadence !== null
                  ? latest === undefined
                    ? t('grid.neverValued', {
                        cadence: tCommon(`cadence.${row.cadence}`).toLowerCase(),
                      })
                    : t('grid.overdueHint', {
                        date: fmt.date(latest.date),
                        cadence: tCommon(`cadence.${row.cadence}`).toLowerCase(),
                      })
                  : null;
              return (
                <TableRow key={entry.key} className="group">
                  {/*
                   * §8.2's cadence-driven freshness indicator is per ROW, because lateness is a fact
                   * about this holding: two holdings in one pot can be one current and one months old.
                   * Only a shared row has a cadence to be late against — a private holding declares no
                   * rhythm at all. Its explanation is the name cell's hint, below the name, since a
                   * cut name opens its own tooltip above it on the same focus.
                   */}
                  <HintedCell
                    hint={overdueHint === null ? [] : [overdueHint]}
                    side="bottom"
                    tabIndex={tabIndexAt(rowIndex, 0)}
                    className={`sticky left-0 z-10 bg-background ${CELL_FOCUS}`}
                  >
                    <div className="flex flex-col">
                      <TruncatingTooltip
                        text={row.name}
                        className="max-w-[200px] text-paragraph-sm-medium"
                      />
                      <span className="text-paragraph-xs text-muted-foreground">
                        {row.baseCurrency}
                      </span>
                      {overdueHint !== null && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="w-fit text-paragraph-mini-medium text-amber-700 cursor-default">
                              {t('grid.overdue')}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>{overdueHint}</TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </HintedCell>
                  {grid.columns.map((column, columnIndex) => {
                    const cell = cellMaps.get(row.investmentId)?.get(column);
                    const tabIndex = tabIndexAt(rowIndex, columnIndex + 1);
                    return cell ? (
                      <ValueCell
                        key={column}
                        row={row}
                        cell={cell}
                        displayCurrency={currency}
                        tabIndex={tabIndex}
                        onOpen={openCell}
                      />
                    ) : (
                      <TableCell
                        key={column}
                        role="gridcell"
                        tabIndex={tabIndex}
                        className={`text-center bg-background transition-colors group-hover:bg-muted/50 ${CELL_FOCUS}`}
                      >
                        <span className="text-muted-foreground">—</span>
                      </TableCell>
                    );
                  })}
                  <TableCell
                    role="gridcell"
                    className="sticky right-0 z-10 bg-background text-center"
                  >
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
                        label={t('grid.lockedAddLabel')}
                        tabIndex={tabIndexAt(rowIndex, columnCount - 1)}
                      />
                    ) : (
                      <RowActionButton
                        icon={Plus}
                        tooltip={t('grid.addSnapshot')}
                        onClick={(e) => handleAddClick(row, e)}
                        tabIndex={tabIndexAt(rowIndex, columnCount - 1)}
                      />
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
