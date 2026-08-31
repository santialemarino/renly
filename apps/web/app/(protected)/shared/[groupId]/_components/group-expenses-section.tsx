'use client';

import { useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Pencil, Plus, Receipt, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { SharedExpenseFormDialog } from '@/app/(protected)/_components/shared-expense-form-dialog';
import { deleteSharedExpense } from '@/app/(protected)/shared/shared-expense-actions';
import { expensePayerDisplay } from '@/app/(protected)/shared/shared-expense-rules';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { EmptyState } from '@/components/empty-state';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import { TablePagination } from '@/components/table-pagination';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Group } from '@/lib/api/groups';
import type { SharedExpense } from '@/lib/api/shared-expenses';
import { useFormatters } from '@/lib/i18n/formatters';

/*
 * Rows per page. The API returns a group's whole history in one response — a shared expense list has
 * no server-side paging — so this is what keeps a household's second year from rendering as one very
 * long table. It is deliberately the same 25 the server-paged lists use, so the hub does not feel
 * like a different kind of list.
 */
const PAGE_SIZE = 25;

interface GroupExpensesSectionProps {
  group: Group;
  expenses: SharedExpense[];
  accounts: Account[];
  creditCards?: CreditCard[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  timeZone?: string;
}

/*
 * What the group has spent together, newest first.
 *
 * Every member may record, edit and delete any of them — the API gates on membership alone, and a
 * group's expenses are the group's rather than their author's. That is the same posture the roster
 * takes towards who may add a member, and the reason there is no per-row ownership here.
 *
 * The row leads with the FULL amount and states the viewer's own share beneath it, which is the
 * opposite of what `/expenses` does — and both are right for where they are. This is the group's
 * ledger, so the group's figure leads; that one is "what did I spend", so the share does.
 */
export function GroupExpensesSection({
  group,
  expenses,
  accounts,
  creditCards,
  preferredCurrencies,
  supportedCurrencies,
  timeZone,
}: GroupExpensesSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<SharedExpense | null>(null);
  const [removing, setRemoving] = useState<SharedExpense | null>(null);
  const [deleting, setDeleting] = useState(false);

  const totalPages = Math.max(1, Math.ceil(expenses.length / PAGE_SIZE));
  /*
   * Clamped rather than reset by an effect: deleting the last row of the last page shortens the list
   * under a page number that no longer exists, and an effect would render one empty frame first.
   */
  const safePage = Math.min(page, totalPages);
  const visible = useMemo(
    () => expenses.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [expenses, safePage],
  );

  /*
   * The row being edited, retained through the dialog's close. Nulling it on close would drop any
   * FORMER seat the expense named from the split rows mid-exit, so the dialog visibly loses a
   * participant on its way out. Retaining it also keeps `useEntityFormDialog` from seeing an entity
   * change on close and resetting a form nobody is looking at any more.
   */
  const lastEditing = useRef<SharedExpense | null>(editing);
  if (editing) lastEditing.current = editing;

  const refresh = () => router.refresh();

  async function onDelete() {
    if (!removing) return;
    setDeleting(true);
    try {
      const result = await deleteSharedExpense(group.id, removing.id);
      if (!result.ok) {
        toast.error(result.conflictDetail || t('expenses.delete.error'));
        return;
      }
      toast.success(t('expenses.delete.success'));
      refresh();
      setRemoving(null);
    } catch {
      toast.error(t('expenses.delete.error'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader title={t('expenses.title')} description={t('expenses.description')} />
        <Button blue onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" />
          {t('expenses.add')}
        </Button>
      </div>

      {expenses.length === 0 ? (
        <EmptyState
          icon={Receipt}
          title={t('expenses.emptyTitle')}
          description={t('expenses.emptyDescription')}
        />
      ) : (
        <div className="flex flex-col gap-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-32">{t('expenses.table.date')}</TableHead>
                <TableHead className="w-44 text-right">{t('expenses.table.amount')}</TableHead>
                <TableHead>{t('expenses.table.category')}</TableHead>
                <TableHead>{t('expenses.table.paidBy')}</TableHead>
                <TableHead>{t('expenses.table.notes')}</TableHead>
                <TableHead className="w-20 text-center">{t('expenses.table.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((expense) => (
                <ExpenseRow
                  key={expense.id}
                  expense={expense}
                  onEdit={() => setEditing(expense)}
                  onRemove={() => setRemoving(expense)}
                />
              ))}
            </TableBody>
          </Table>

          <TablePagination
            page={safePage}
            totalPages={totalPages}
            totalLabel={t('expenses.table.total', { total: expenses.length })}
            onPageChange={setPage}
          />
        </div>
      )}

      <SharedExpenseFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        group={group}
        accounts={accounts}
        creditCards={creditCards}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        timeZone={timeZone}
        onSuccess={refresh}
      />

      {/* The edited row stays mounted through the close: only `open` is toggled, so the dialog does
          not blank out mid-animation. */}
      <SharedExpenseFormDialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        group={group}
        expense={editing ?? lastEditing.current ?? undefined}
        accounts={accounts}
        creditCards={creditCards}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        timeZone={timeZone}
        onSuccess={refresh}
      />

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        entity={removing}
        title={t('expenses.delete.title')}
        description={() => t('expenses.delete.description')}
        loading={deleting}
        loadingLabel={t('form.cta.loading')}
        confirmLabel={t('expenses.delete.confirm')}
        cancelLabel={t('form.cancel')}
        onConfirm={onDelete}
      />
    </div>
  );
}

/*
 * One shared expense.
 *
 * "Paid by" never names a person for money that came out of a shared account, however that account's
 * ownership happens to be divided — including a pot with exactly one owner, where that owner really
 * does front the whole amount. Saying "Nico paid" there would claim he paid personally for money that
 * came out of the joint account, which is a statement about a different pot of money entirely.
 */
function ExpenseRow({
  expense,
  onEdit,
  onRemove,
}: {
  expense: SharedExpense;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const payer = expensePayerDisplay(expense);

  return (
    <TableRow>
      <TableCell>{fmt.date(expense.date)}</TableCell>
      <TableCell className="text-right text-paragraph-sm tabular-nums">
        {/*
         * The code is part of the figure here, unlike on `/expenses`: a group's list holds every
         * currency it has ever spent in, side by side and never converted — so a bare 120 beside a
         * bare 90,000 would leave the reader to guess which is dollars. The share beneath is in the
         * same currency, so it does not repeat it.
         */}
        {`${fmt.amount(expense.amount, expense.currency)} ${expense.currency}`}
        {/* Null when the viewer took no part in this one, which is a real and unremarkable state —
            somebody paid for a meal they were not at. The row then states only the group's figure. */}
        {expense.myShare !== null && (
          <span className="block text-paragraph-xs text-muted-foreground">
            {t('expenses.table.yourShare', {
              amount: fmt.amount(expense.myShare, expense.currency),
            })}
          </span>
        )}
      </TableCell>
      <TableCell>{expense.category ? tCommon(`categories.${expense.category}`) : '—'}</TableCell>
      <TableCell className="text-paragraph-sm">
        {payer.kind === 'member'
          ? payer.displayName
          : payer.accountName
            ? t('expenses.table.jointNamed', { account: payer.accountName })
            : t('expenses.table.joint')}
      </TableCell>
      <TableCell className="max-w-48 truncate text-muted-foreground">
        {expense.notes ?? '—'}
      </TableCell>
      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-center gap-x-1">
          <RowActionButton
            icon={Pencil}
            tooltip={t('expenses.actions.edit')}
            ariaLabel="Edit"
            onClick={onEdit}
          />
          <RowActionButton
            icon={Trash2}
            tooltip={t('expenses.actions.delete')}
            ariaLabel="Delete"
            variant="destructive"
            onClick={onRemove}
          />
        </div>
      </TableCell>
    </TableRow>
  );
}
