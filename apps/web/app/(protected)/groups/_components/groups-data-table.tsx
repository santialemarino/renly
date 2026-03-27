'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUp, ChevronsUpDown, Pencil, Trash2 } from 'lucide-react';
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
import { GroupDeleteFormDialog } from '@/app/(protected)/groups/_components/group-delete-form-dialog';
import { GroupFormDialog } from '@/app/(protected)/groups/_components/group-form-dialog';
import { ROUTES } from '@/config/routes';
import type { InvestmentGroup } from '@/lib/api/groups';

type SortField = 'id' | 'name';
type SortOrder = 'asc' | 'desc';

function SortIcon({
  column,
  sortBy,
  sortOrder,
}: {
  column: SortField;
  sortBy: SortField | null;
  sortOrder: SortOrder;
}) {
  const active = sortBy === column;
  const isAsc = active && sortOrder === 'asc';
  const isDesc = active && sortOrder === 'desc';
  return (
    <span className="grid shrink-0 group-focus-visible/sort:animate-focus-bump">
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

interface GroupsDataTableProps {
  groups: InvestmentGroup[];
  investments: { id: number; name: string }[];
  sortBy?: string;
  sortOrder?: SortOrder;
}

export function GroupsDataTable({ groups, investments, sortBy, sortOrder }: GroupsDataTableProps) {
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
          <TableHead>
            <button
              type="button"
              onClick={() => handleSortChange('name')}
              className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
            >
              {t('table.name')}
              <SortIcon column="name" sortBy={activeSortBy} sortOrder={activeSortOrder} />
            </button>
          </TableHead>
          <TableHead>{t('table.investments')}</TableHead>
          <TableHead className="w-20 text-center">{t('table.actions')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} className="py-10 rounded-sm text-center text-muted-foreground">
              {t('table.empty')}
            </TableCell>
          </TableRow>
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
  const t = useTranslations('groups');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const investmentNames = group.investmentIds
    .map((id) => investmentMap.get(id))
    .filter(Boolean)
    .join(', ');

  return (
    <>
      <TableRow>
        <TableCell className="text-muted-foreground">{group.id}</TableCell>
        <TableCell className="text-paragraph-sm-medium">{group.name}</TableCell>
        <TableCell className="text-paragraph-sm text-muted-foreground max-w-md truncate">
          {investmentNames || t('table.noInvestments')}
        </TableCell>
        <TableCell className="text-center">
          <div className="flex items-center justify-center gap-x-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8"
                  onClick={() => setEditOpen(true)}
                  aria-label={t('form.editTitle')}
                >
                  <Pencil className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('form.editTitle')}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground hover:text-destructive"
                  onClick={() => setDeleteOpen(true)}
                  aria-label={t('delete.title')}
                >
                  <Trash2 className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('delete.title')}</TooltipContent>
            </Tooltip>
          </div>
        </TableCell>
      </TableRow>

      {editOpen && (
        <GroupFormDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          group={group}
          investments={investments}
          onSuccess={onSuccess}
        />
      )}
      {deleteOpen && (
        <GroupDeleteFormDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          group={group}
          onSuccess={onSuccess}
        />
      )}
    </>
  );
}
