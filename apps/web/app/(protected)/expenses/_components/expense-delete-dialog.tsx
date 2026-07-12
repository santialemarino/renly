'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { resolveCursorToast } from '@/app/(protected)/expenses/_components/cursor-toast';
import { deleteExpense } from '@/app/(protected)/expenses/expenses-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { Expense } from '@/lib/api/expenses';
import { formatAmount } from '@/lib/utils/currency';

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
  const locale = useLocale();
  const t = useTranslations('expenses');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      const cursorChange = await deleteExpense(expense.id);
      const baseMessage = t('delete.success');
      if (cursorChange) {
        const resolution = resolveCursorToast(cursorChange, 'reverse', locale);
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
          amount: formatAmount(e.amount, locale, e.currency),
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
