'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, ArchiveRestore, Landmark, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@repo/ui/components';
import { AccountDeleteDialog } from '@/app/(protected)/accounts/_components/account-delete-dialog';
import { AccountFormDialog } from '@/app/(protected)/accounts/_components/account-form-dialog';
import { archiveAccount, unarchiveAccount } from '@/app/(protected)/accounts/account-actions';
import { RowActionButton } from '@/components/row-action-button';
import { SortableTableHead } from '@/components/sortable-table-head';
import { TableEmptyRow } from '@/components/table-empty-row';
import { ROUTES } from '@/config/routes';
import type { Account, AccountSortField } from '@/lib/api/accounts';
import { useTableSort } from '@/lib/hooks/use-table-sort';
import { useFormatters } from '@/lib/i18n/formatters';

interface AccountsTableProps {
  accounts: Account[];
  preferredCurrencies?: string[];
  firstRun?: boolean;
}

export function AccountsTable({ accounts, preferredCurrencies, firstRun }: AccountsTableProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts');
  const router = useRouter();
  const { sortBy, sortOrder, handleSortChange, isPending } = useTableSort<AccountSortField>(
    ROUTES.accounts,
  );
  const [editAccount, setEditAccount] = useState<Account | null>(null);
  const [deleteState, setDeleteState] = useState<Account | null>(null);
  const [archivingId, setArchivingId] = useState<number | null>(null);

  async function handleArchive(account: Account) {
    setArchivingId(account.id);
    try {
      await archiveAccount(account.id);
      toast.success(t('actions.archiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.archiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  async function handleUnarchive(account: Account) {
    setArchivingId(account.id);
    try {
      await unarchiveAccount(account.id);
      toast.success(t('actions.unarchiveSuccess'));
      router.refresh();
    } catch {
      toast.error(t('actions.unarchiveError'));
    } finally {
      setArchivingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead
                label={t('table.name')}
                column="name"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.type')}
                column="type"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <SortableTableHead
                label={t('table.currency')}
                column="currency"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead className="text-right">{t('table.balance')}</TableHead>
              <SortableTableHead
                label={t('table.openingDate')}
                column="opening_date"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSortChange}
              />
              <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.length === 0 ? (
              <TableEmptyRow
                colSpan={6}
                firstRun={firstRun}
                icon={Landmark}
                title={t('table.emptyTitle')}
                description={t('table.emptyDescription')}
                plain={t('table.empty')}
              />
            ) : (
              accounts.map((a) => (
                <TableRow key={a.id} className={!a.isActive ? 'opacity-60' : undefined}>
                  <TableCell className="text-paragraph-sm-medium">{a.name}</TableCell>
                  <TableCell className="text-muted-foreground">{t(`types.${a.type}`)}</TableCell>
                  <TableCell className="text-muted-foreground">{a.currency}</TableCell>
                  <TableCell className="text-right text-paragraph-sm tabular-nums">
                    {fmt.amount(a.balance, a.currency)}
                  </TableCell>
                  <TableCell>{fmt.date(a.openingDate)}</TableCell>
                  <TableCell className="text-center">
                    {!a.isActive ? (
                      <div className="flex items-center justify-center gap-x-1">
                        <RowActionButton
                          icon={ArchiveRestore}
                          tooltip={t('actions.unarchive')}
                          ariaLabel="Unarchive"
                          onClick={() => handleUnarchive(a)}
                          disabled={archivingId === a.id}
                        />
                        <RowActionButton
                          icon={Trash2}
                          tooltip={t('actions.delete')}
                          ariaLabel="Delete"
                          variant="destructive"
                          onClick={() => setDeleteState(a)}
                        />
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-x-1">
                        <RowActionButton
                          icon={Pencil}
                          tooltip={t('actions.edit')}
                          ariaLabel="Edit"
                          onClick={() => setEditAccount(a)}
                        />
                        <RowActionButton
                          icon={Archive}
                          tooltip={t('actions.archive')}
                          ariaLabel="Archive"
                          variant="muted"
                          onClick={() => handleArchive(a)}
                          disabled={archivingId === a.id}
                        />
                        <RowActionButton
                          icon={Trash2}
                          tooltip={t('actions.delete')}
                          ariaLabel="Delete"
                          variant="destructive"
                          onClick={() => setDeleteState(a)}
                        />
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <AccountFormDialog
        open={!!editAccount}
        onOpenChange={(open) => {
          if (!open) setEditAccount(null);
        }}
        account={editAccount ?? undefined}
        preferredCurrencies={preferredCurrencies}
        onSuccess={() => router.refresh()}
      />

      <AccountDeleteDialog
        open={!!deleteState}
        onOpenChange={(open) => {
          if (!open) setDeleteState(null);
        }}
        account={deleteState}
        onSuccess={() => router.refresh()}
      />
    </div>
  );
}
