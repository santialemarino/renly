'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FolderOpen, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { CollectionDeleteFormDialog } from '@/app/(protected)/collections/_components/collection-delete-form-dialog';
import { CollectionFormDialog } from '@/app/(protected)/collections/_components/collection-form-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { InvestmentCollection } from '@/lib/api/collections';
import type { SortOrder } from '@/lib/api/types';
import { useFormatters } from '@/lib/i18n/formatters';

type SortField = 'id' | 'name';

interface CollectionsDataTableProps {
  collections: InvestmentCollection[];
  investments: { id: number; name: string }[];
  sortBy?: string;
  sortOrder?: SortOrder;
  firstRun?: boolean;
}

export function CollectionsDataTable({
  collections,
  investments,
  sortBy,
  sortOrder,
  firstRun,
}: CollectionsDataTableProps) {
  const t = useTranslations('collections');
  const router = useRouter();
  const searchParams = useSearchParams();

  const investmentMap = new Map(investments.map((inv) => [inv.id, inv.name]));

  const activeSortBy = (sortBy as SortField | undefined) ?? null;
  const activeSortOrder = sortOrder ?? 'asc';

  function handleSortChange(column: SortField) {
    const qs = new URLSearchParams(searchParams.toString());
    if (activeSortBy === column) {
      if (activeSortOrder === 'asc') {
        qs.set('sort_by', column);
        qs.set('sort_order', 'desc');
      } else {
        qs.delete('sort_by');
        qs.delete('sort_order');
      }
    } else {
      qs.set('sort_by', column);
      qs.set('sort_order', 'asc');
    }
    router.push(`${ROUTES.collections}?${qs.toString()}`, { scroll: false });
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12">{t('table.id')}</TableHead>
          <SortableTableHead
            label={t('table.name')}
            column="name"
            sortBy={activeSortBy}
            sortOrder={activeSortOrder}
            onSort={handleSortChange}
          />
          <TableHead className="w-24">{t('table.target')}</TableHead>
          <TableHead>{t('table.investments')}</TableHead>
          <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {collections.length === 0 ? (
          <TableEmptyRow
            colSpan={5}
            firstRun={firstRun}
            icon={FolderOpen}
            title={t('table.emptyTitle')}
            description={t('table.emptyDescription')}
            plain={t('table.empty')}
          />
        ) : (
          collections.map((collection) => (
            <CollectionRow
              key={collection.id}
              collection={collection}
              investmentMap={investmentMap}
              investments={investments}
              onSuccess={() => router.refresh()}
            />
          ))
        )}
      </TableBody>
    </Table>
  );
}

function CollectionRow({
  collection,
  investmentMap,
  investments,
  onSuccess,
}: {
  collection: InvestmentCollection;
  investmentMap: Map<number, string>;
  investments: { id: number; name: string }[];
  onSuccess: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('collections');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const investmentNames = fmt.list(
    collection.investmentIds
      .map((id) => investmentMap.get(id))
      .filter((name): name is string => name != null),
  );

  return (
    <>
      <TableRow>
        <TableCell className="text-muted-foreground">{collection.id}</TableCell>
        <TableCell className="text-paragraph-sm-medium">{collection.name}</TableCell>
        <TableCell className="text-paragraph-sm text-muted-foreground">
          {collection.targetPercentage != null
            ? `${collection.targetPercentage}%`
            : t('table.noTarget')}
        </TableCell>
        <TableCell className="max-w-md text-paragraph-sm text-muted-foreground truncate">
          {investmentNames || t('table.noInvestments')}
        </TableCell>
        <TableCell className="text-center">
          <div className="flex items-center justify-center gap-x-1">
            <RowActionButton
              icon={Pencil}
              tooltip={t('form.editTitle')}
              ariaLabel="Edit"
              onClick={() => setEditOpen(true)}
            />
            <RowActionButton
              icon={Trash2}
              tooltip={t('delete.title')}
              ariaLabel="Delete"
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            />
          </div>
        </TableCell>
      </TableRow>

      <CollectionFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        collection={collection}
        investments={investments}
        onSuccess={onSuccess}
      />
      <CollectionDeleteFormDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        collection={collection}
        onSuccess={onSuccess}
      />
    </>
  );
}
