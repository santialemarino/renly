'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FolderOpen, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { GroupDeleteFormDialog } from '@/app/(protected)/groups/_components/group-delete-form-dialog';
import { GroupFormDialog } from '@/app/(protected)/groups/_components/group-form-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/groups';
import type { SortOrder } from '@/lib/api/types';
import { useFormatters } from '@/lib/i18n/formatters';

type SortField = 'id' | 'name';

interface GroupsDataTableProps {
  groups: InvestmentGroup[];
  investments: { id: number; name: string }[];
  sortBy?: string;
  sortOrder?: SortOrder;
  firstRun?: boolean;
}

export function GroupsDataTable({
  groups,
  investments,
  sortBy,
  sortOrder,
  firstRun,
}: GroupsDataTableProps) {
  const t = useTranslations('groups');
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
    router.push(`${ROUTES.groups}?${qs.toString()}`, { scroll: false });
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
        {groups.length === 0 ? (
          <TableEmptyRow
            colSpan={5}
            firstRun={firstRun}
            icon={FolderOpen}
            title={t('table.emptyTitle')}
            description={t('table.emptyDescription')}
            plain={t('table.empty')}
          />
        ) : (
          groups.map((group) => (
            <GroupRow
              key={group.id}
              group={group}
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

function GroupRow({
  group,
  investmentMap,
  investments,
  onSuccess,
}: {
  group: InvestmentGroup;
  investmentMap: Map<number, string>;
  investments: { id: number; name: string }[];
  onSuccess: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('groups');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const investmentNames = fmt.list(
    group.investmentIds
      .map((id) => investmentMap.get(id))
      .filter((name): name is string => name != null),
  );

  return (
    <>
      <TableRow>
        <TableCell className="text-muted-foreground">{group.id}</TableCell>
        <TableCell className="text-paragraph-sm-medium">{group.name}</TableCell>
        <TableCell className="text-paragraph-sm text-muted-foreground">
          {group.targetPercentage != null ? `${group.targetPercentage}%` : t('table.noTarget')}
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

      <GroupFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        group={group}
        investments={investments}
        onSuccess={onSuccess}
      />
      <GroupDeleteFormDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        group={group}
        onSuccess={onSuccess}
      />
    </>
  );
}
