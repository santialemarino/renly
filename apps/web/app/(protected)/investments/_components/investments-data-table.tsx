'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, Pencil, Rows3 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { InvestmentArchiveFormDialog } from '@/app/(protected)/investments/_components/investment-archive-form-dialog';
import { InvestmentFormDialog } from '@/app/(protected)/investments/_components/investment-form-dialog';
import { unarchiveInvestment } from '@/app/(protected)/investments/investments-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { TablePagination } from '@/components/table-pagination';
import { ROUTES } from '@/config/routes';
import type {
  Investment,
  InvestmentGroup,
  InvestmentListResponse,
  InvestmentSortField,
} from '@/lib/api/investments';
import { useTableSort } from '@/lib/hooks/use-table-sort';

function RowActions({
  investment,
  groups,
  preferredCurrencies,
  supportedCurrencies,
  onSuccess,
}: {
  investment: Investment;
  groups: InvestmentGroup[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  onSuccess: () => void;
}) {
  const t = useTranslations('investments');
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
        groups={groups}
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
  groups,
  preferredCurrencies,
  supportedCurrencies,
  firstRun,
}: {
  data: InvestmentListResponse;
  groups: InvestmentGroup[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  firstRun?: boolean;
}) {
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, navigate, isPending } =
    useTableSort<InvestmentSortField>(ROUTES.investments, { resetPage: true });

  function handlePageChange(page: number) {
    navigate({ page: page > 1 ? String(page) : null });
  }

  function handleRowClick(investment: Investment) {
    router.push(`${ROUTES.investorDashboard}?investment_id=${investment.id}`);
  }

  const { items, total, page, pageSize } = data;
  const totalPages = Math.ceil(total / pageSize);

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
              <TableHead>{t('table.groups')}</TableHead>
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
              items.map((investment) => (
                <TableRow
                  key={investment.id}
                  className="cursor-pointer"
                  onClick={() => handleRowClick(investment)}
                >
                  <TableCell className="text-muted-foreground">{investment.id}</TableCell>
                  <TableCell className="text-paragraph-sm-medium">{investment.name}</TableCell>
                  <TableCell>
                    {investment.groups.length > 0 ? (
                      <div className="flex flex-wrap gap-x-1 gap-y-1">
                        {investment.groups.map((g) => (
                          <span
                            key={g.id}
                            className="px-1.5 py-0.5 rounded text-paragraph-xs bg-muted text-muted-foreground"
                          >
                            {g.name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>{tCommon(`categories.${investment.category}`)}</TableCell>
                  <TableCell>{investment.baseCurrency}</TableCell>
                  <TableCell className="text-muted-foreground font-mono">
                    {investment.ticker ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {investment.broker ?? '—'}
                  </TableCell>
                  <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      investment={investment}
                      groups={groups}
                      preferredCurrencies={preferredCurrencies}
                      supportedCurrencies={supportedCurrencies}
                      onSuccess={() => router.refresh()}
                    />
                  </TableCell>
                </TableRow>
              ))
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
