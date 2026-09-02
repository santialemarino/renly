'use client';

import { useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CircleDollarSign, Pencil, Plus, Trash2 } from 'lucide-react';
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
import { SharedIncomeFormDialog } from '@/app/(protected)/_components/shared-income-form-dialog';
import { deleteSharedIncome } from '@/app/(protected)/shared/shared-income-actions';
import { incomeHolderDisplay } from '@/app/(protected)/shared/shared-income-rules';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { EmptyState } from '@/components/empty-state';
import { RowActionButton } from '@/components/row-action-button';
import { SectionHeader } from '@/components/section-header';
import { TablePagination } from '@/components/table-pagination';
import type { Account } from '@/lib/api/accounts';
import type { Group } from '@/lib/api/groups';
import type { SharedIncome } from '@/lib/api/shared-income';
import { useFormatters } from '@/lib/i18n/formatters';

/*
 * Rows per page. The API returns a group's whole history in one response — a shared income list has no
 * server-side paging — so this is what keeps a household's second year from rendering as one very long
 * table. Deliberately the same 25 the expenses section beside it uses.
 */
const PAGE_SIZE = 25;

interface GroupIncomeSectionProps {
  group: Group;
  income: SharedIncome[];
  accounts: Account[];
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  timeZone?: string;
}

/*
 * What the group has earned together, newest first.
 *
 * Every member may record, edit and delete any of it — the API gates on membership alone, and a
 * group's income is the group's rather than its author's. Same posture as the expenses section, and
 * the same reason there is no per-row ownership here.
 *
 * The row leads with the FULL amount and states the viewer's own share beneath it, which is the
 * opposite of what `/income` does — and both are right for where they are. This is the group's
 * ledger, so the group's figure leads; that one is "what did I earn", so the share does.
 */
export function GroupIncomeSection({
  group,
  income,
  accounts,
  preferredCurrencies,
  supportedCurrencies,
  timeZone,
}: GroupIncomeSectionProps) {
  const t = useTranslations('shared');
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<SharedIncome | null>(null);
  const [removing, setRemoving] = useState<SharedIncome | null>(null);
  const [deleting, setDeleting] = useState(false);

  const totalPages = Math.max(1, Math.ceil(income.length / PAGE_SIZE));
  /*
   * Clamped rather than reset by an effect: deleting the last row of the last page shortens the list
   * under a page number that no longer exists, and an effect would render one empty frame first.
   */
  const safePage = Math.min(page, totalPages);
  const visible = useMemo(
    () => income.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [income, safePage],
  );

  /*
   * The row being edited, retained through the dialog's close. Nulling it on close would drop any
   * FORMER seat the row named from the split rows mid-exit, so the dialog visibly loses a participant
   * on its way out. Retaining it also keeps `useEntityFormDialog` from seeing an entity change on
   * close and resetting a form nobody is looking at any more.
   */
  const lastEditing = useRef<SharedIncome | null>(editing);
  if (editing) lastEditing.current = editing;

  const refresh = () => router.refresh();

  async function onDelete() {
    if (!removing) return;
    setDeleting(true);
    try {
      const result = await deleteSharedIncome(group.id, removing.id);
      if (!result.ok) {
        toast.error(result.conflictDetail || t('income.delete.error'));
        return;
      }
      toast.success(t('income.delete.success'));
      refresh();
      setRemoving(null);
    } catch {
      toast.error(t('income.delete.error'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <SectionHeader title={t('income.title')} description={t('income.description')} />
        <Button blue onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" />
          {t('income.add')}
        </Button>
      </div>

      {income.length === 0 ? (
        <EmptyState
          icon={CircleDollarSign}
          title={t('income.emptyTitle')}
          description={t('income.emptyDescription')}
        />
      ) : (
        <div className="flex flex-col gap-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-32">{t('income.table.date')}</TableHead>
                <TableHead className="w-44 text-right">{t('income.table.amount')}</TableHead>
                <TableHead>{t('income.table.source')}</TableHead>
                <TableHead>{t('income.table.wentTo')}</TableHead>
                <TableHead>{t('income.table.notes')}</TableHead>
                <TableHead className="w-20 text-center">{t('income.table.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((row) => (
                <IncomeRow
                  key={row.id}
                  income={row}
                  onEdit={() => setEditing(row)}
                  onRemove={() => setRemoving(row)}
                />
              ))}
            </TableBody>
          </Table>

          <TablePagination
            page={safePage}
            totalPages={totalPages}
            totalLabel={t('income.table.total', { total: income.length })}
            onPageChange={setPage}
          />
        </div>
      )}

      <SharedIncomeFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        group={group}
        accounts={accounts}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        timeZone={timeZone}
        onSuccess={refresh}
      />

      {/* The edited row stays mounted through the close: only `open` is toggled, so the dialog does
          not blank out mid-animation. */}
      <SharedIncomeFormDialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        group={group}
        income={editing ?? lastEditing.current ?? undefined}
        accounts={accounts}
        preferredCurrencies={preferredCurrencies}
        supportedCurrencies={supportedCurrencies}
        timeZone={timeZone}
        onSuccess={refresh}
      />

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        entity={removing}
        title={t('income.delete.title')}
        description={() => t('income.delete.description')}
        loading={deleting}
        loadingLabel={t('form.cta.loading')}
        confirmLabel={t('income.delete.confirm')}
        cancelLabel={t('form.cancel')}
        onConfirm={onDelete}
      />
    </div>
  );
}

/*
 * One piece of shared income.
 *
 * "Went to" never names a person for money that arrived in a shared account, however that account's
 * ownership happens to be divided — including a pot with exactly one owner, where that owner really
 * does receive the whole amount. Saying "Nico received it" there would claim he took it personally
 * when it went into the joint account, which is a statement about a different pot of money entirely.
 *
 * The source cell can be empty for two different reasons and says nothing either way: the row names no
 * asset, or it names one sitting in a pot this viewer is not permitted to see. Neither is worth a
 * different sentence — both mean "not something this reader can attribute".
 */
function IncomeRow({
  income,
  onEdit,
  onRemove,
}: {
  income: SharedIncome;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const fmt = useFormatters();
  const t = useTranslations('shared');

  const holder = incomeHolderDisplay(income);

  return (
    <TableRow>
      <TableCell>{fmt.date(income.date)}</TableCell>
      <TableCell className="text-right text-paragraph-sm tabular-nums">
        {/*
         * The code is part of the figure here, unlike on `/income`: a group's list holds every
         * currency it has ever earned in, side by side and never converted — so a bare 120 beside a
         * bare 90,000 would leave the reader to guess which is dollars. The share beneath is in the
         * same currency, so it does not repeat it.
         */}
        {`${fmt.amount(income.amount, income.currency)} ${income.currency}`}
        {/* Null when the viewer is entitled to none of this one, which is a real and unremarkable
            state — a custodian collecting rent on somebody else's behalf. The row then states only
            the group's figure. */}
        {income.myShare !== null && (
          <span className="block text-paragraph-xs text-muted-foreground">
            {t('income.table.yourShare', {
              amount: fmt.amount(income.myShare, income.currency),
            })}
          </span>
        )}
      </TableCell>
      <TableCell className="max-w-40 truncate text-paragraph-sm">
        {income.sourceInvestmentName ?? t('income.table.noSource')}
      </TableCell>
      <TableCell className="text-paragraph-sm">
        {holder.kind === 'member'
          ? holder.displayName
          : holder.accountName
            ? t('income.table.jointNamed', { account: holder.accountName })
            : t('income.table.joint')}
      </TableCell>
      <TableCell className="max-w-48 truncate text-muted-foreground">
        {income.notes ?? '—'}
      </TableCell>
      <TableCell className="text-center" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-center gap-x-1">
          <RowActionButton
            icon={Pencil}
            tooltip={t('income.actions.edit')}
            ariaLabel="Edit"
            onClick={onEdit}
          />
          <RowActionButton
            icon={Trash2}
            tooltip={t('income.actions.delete')}
            ariaLabel="Delete"
            variant="destructive"
            onClick={onRemove}
          />
        </div>
      </TableCell>
    </TableRow>
  );
}
