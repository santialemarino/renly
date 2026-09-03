'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, Lock, Pencil, Rows3 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { InvestmentArchiveFormDialog } from '@/app/(protected)/investments/_components/investment-archive-form-dialog';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { unarchiveInvestment } from '@/app/(protected)/investments/investments-actions';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { TableSectionRow } from '@/components/table-section-row';
import { ROUTES, sharedPotPath } from '@/config/routes';
import type { InvestmentCollection } from '@/lib/api/collections';
import type {
  Investment,
  InvestmentListResponse,
  InvestmentSortField,
} from '@/lib/api/investments';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { bySectionPot, sectionedRows } from '@/lib/list-scope';

function RowActions({
  investment,
  collections,
  preferredCurrencies,
  supportedCurrencies,
  canWrite,
  onSuccess,
}: {
  investment: Investment;
  collections: InvestmentCollection[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  // Write access to the pot that owns the row, granted per (pot, member) and stated on the SECTION.
  // Always true for the caller's own holdings.
  canWrite: boolean;
  onSuccess: () => void;
}) {
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');
  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [unarchiving, setUnarchiving] = useState(false);

  async function handleUnarchive(e: React.MouseEvent) {
    e.stopPropagation();
    setUnarchiving(true);
    try {
      await unarchiveInvestment(investment.id);
      toast.success(t('unarchiveSuccess'));
      onSuccess();
    } catch {
      toast.error(t('unarchiveError'));
    } finally {
      setUnarchiving(false);
    }
  }

  /*
   * A co-owned holding is editable by whoever the pot granted write access to, and by nobody else.
   * The indicator rather than a disabled button, because a Radix tooltip never fires on a disabled
   * trigger and the explanation would never render — so the action is hidden and its absence is what
   * gets explained, right where the button was.
   */
  if (!canWrite) {
    return (
      <div className="flex items-center justify-center">
        <RowLockedIndicator
          icon={Lock}
          tooltip={tCommon('lockedRow.sharedHolding')}
          ariaLabel="Managed by the pot"
        />
      </div>
    );
  }

  if (!investment.isActive) {
    return (
      <div className="flex items-center justify-center">
        <RowActionButton
          icon={ArchiveRestore}
          tooltip={t('actions.unarchive')}
          ariaLabel="Unarchive"
          onClick={handleUnarchive}
          disabled={unarchiving}
        />
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center justify-center gap-x-1">
        <RowActionButton
          icon={Pencil}
          tooltip={t('actions.edit')}
          ariaLabel="Edit"
          onClick={(e) => {
            e.stopPropagation();
            setEditOpen(true);
          }}
        />
        <RowActionButton
          icon={Archive}
          tooltip={t('actions.archive')}
          ariaLabel="Archive"
          variant="muted"
          onClick={(e) => {
            e.stopPropagation();
            setArchiveOpen(true);
          }}
        />
      </div>

      <InvestmentFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        investment={investment}
        collections={collections}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        onSuccess={onSuccess}
      />

      <InvestmentArchiveFormDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        investment={investment}
        onSuccess={onSuccess}
      />
    </>
  );
}

export function InvestmentsDataTable({
  data,
  collections,
  preferredCurrencies,
  supportedCurrencies,
  firstRun,
}: {
  data: InvestmentListResponse;
  collections: InvestmentCollection[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  firstRun?: boolean;
}) {
  const t = useTranslations('investments');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, navigate, isPending } =
    useTableSort<InvestmentSortField>(ROUTES.investments, { resetPage: true });

  function handlePageChange(page: number) {
    navigate({ page: page > 1 ? String(page) : null });
  }

  /*
   * A private row opens the investor dashboard; a co-owned one opens its POT.
   *
   * Not a convenience: the investor dashboard is private by decision (PR 8a, decision 7) because a
   * co-owned holding's TWR is the pot's — your exposure moves whenever units are issued, so a
   * per-investment return attributed to you is wrong in a way no label repairs. Its endpoint is
   * owner-filtered and would 404. The pot page is where a shared holding's value, ownership and
   * history actually live.
   */
  function handleRowClick(investment: Investment) {
    router.push(
      investment.potId !== null
        ? sharedPotPath(investment.potId)
        : `${ROUTES.investorDashboard}?investment_id=${investment.id}`,
    );
  }

  const { items, total, page, pageSize, sections } = data;
  const totalPages = Math.ceil(total / pageSize);
  const rendered = sectionedRows(items, sections, {
    rowKey: (investment) => String(investment.id),
    scopeKey: (investment) => investment.potId,
    sectionKey: bySectionPot,
  });
  // Write access is a property of the section, so the row reads it from there rather than carrying a
  // copy. A row with no section is the caller's own, which they may always change.
  const writableByPot = new Map(sections.map((section) => [section.potId, section.canWrite]));

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">{t('table.id')}</TableHead>
              <SortableTableHead
                label={t('table.name')}
                column="name"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.collections')}</TableHead>
              <SortableTableHead
                label={t('table.category')}
                column="category"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.currency')}
                column="base_currency"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead>{t('table.ticker')}</TableHead>
              <SortableTableHead
                label={t('table.broker')}
                column="broker"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableEmptyRow
                colSpan={8}
                firstRun={firstRun}
                icon={Rows3}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              rendered.map((entry) =>
                entry.kind === 'header' ? (
                  <TableSectionRow
                    key={entry.key}
                    section={entry.section}
                    colSpan={8}
                    countLabel={t('table.sectionCount', { count: entry.section.count })}
                  />
                ) : (
                  <InvestmentRow
                    key={entry.key}
                    investment={entry.row}
                    collections={collections}
                    preferredCurrencies={preferredCurrencies}
                    supportedCurrencies={supportedCurrencies}
                    canWrite={writableByPot.get(entry.row.potId) ?? true}
                    onRowClick={handleRowClick}
                    onSuccess={() => router.refresh()}
                  />
                ),
              )
            )}
          </TableBody>
        </Table>
      </div>

      <TablePagination
        page={page}
        totalPages={totalPages}
        totalLabel={t('table.total', { total })}
        onPageChange={handlePageChange}
      />
    </div>
  );
}

// One investment row. Extracted so the section walk composes rows and headers by mapping one list,
// rather than nesting a conditional around forty lines of markup.
function InvestmentRow({
  investment,
  collections,
  preferredCurrencies,
  supportedCurrencies,
  canWrite,
  onRowClick,
  onSuccess,
}: {
  investment: Investment;
  collections: InvestmentCollection[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  canWrite: boolean;
  onRowClick: (investment: Investment) => void;
  onSuccess: () => void;
}) {
  const tCommon = useTranslations('common');

  return (
    <TableRow className="cursor-pointer" onClick={() => onRowClick(investment)}>
      <TableCell className="text-muted-foreground">{investment.id}</TableCell>
      <TableCell className="text-paragraph-sm-medium">{investment.name}</TableCell>
      <TableCell>
        {investment.collections.length > 0 ? (
          <div className="flex flex-wrap gap-x-1 gap-y-1">
            {investment.collections.map((c) => (
              <span
                key={c.id}
                className="px-1.5 py-0.5 rounded text-paragraph-xs bg-muted text-muted-foreground"
              >
                {c.name}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>{tCommon(`categories.${investment.category}`)}</TableCell>
      <TableCell>{investment.baseCurrency}</TableCell>
      <TableCell className="text-muted-foreground font-mono">{investment.ticker ?? '—'}</TableCell>
      <TableCell className="text-muted-foreground">{investment.broker ?? '—'}</TableCell>
      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
        <RowActions
          investment={investment}
          collections={collections}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          canWrite={canWrite}
          onSuccess={onSuccess}
        />
      </TableCell>
    </TableRow>
  );
}
