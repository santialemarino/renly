'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { resolveCursorToast } from '@/app/(protected)/expenses/_components/cursor-toast';
import { deleteExpense } from '@/app/(protected)/expenses/expenses-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { Expense } from '@/lib/api/expenses';
import { useFormatters } from '@/lib/i18n/formatters';

interface ExpenseDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  expense: Expense;
  onSuccess: () => void;
}

export function ExpenseDeleteDialog({
  open,
  onOpenChange,
  expense,
  onSuccess,
}: ExpenseDeleteDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('expenses');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      const result = await deleteExpense(expense.id);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      const cursorChange = result.reverse;
      const baseMessage = t('delete.success');
      if (cursorChange) {
        const resolution = resolveCursorToast(cursorChange, 'reverse', fmt.date);
        if (resolution) {
          toast.success(`${baseMessage} ${t(`form.${resolution.key}`, resolution.params)}`);
        } else {
          toast.success(baseMessage);
        }
      } else {
        toast.success(baseMessage);
      }
      onOpenChange(false);
      onSuccess();
    } catch {
      toast.error(t('delete.error'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={expense}
      title={t('delete.title')}
      description={(e) =>
        t('delete.confirm', {
          amount: fmt.amount(e.amount, e.currency),
          currency: e.currency,
        })
      }
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
      cancelLabel={t('form.cancel')}
    />
  );
}
