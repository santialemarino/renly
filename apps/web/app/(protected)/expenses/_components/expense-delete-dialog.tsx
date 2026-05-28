'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import { resolveCursorToast } from '@/app/(protected)/expenses/_components/cursor-toast';
import { deleteExpense } from '@/app/(protected)/expenses/expenses-actions';
import type { Expense } from '@/lib/api/expenses';
import type { Installment } from '@/lib/api/installments';
import { formatAmount } from '@/lib/utils/currency';

interface ExpenseDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  expense: Expense;
  activeInstallments?: Installment[];
  onSuccess: () => void;
}

export function ExpenseDeleteDialog({
  open,
  onOpenChange,
  expense,
  activeInstallments,
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
        const resolution = resolveCursorToast(cursorChange, 'reverse', locale, activeInstallments);
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('delete.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">
          {t('delete.confirm', {
            amount: formatAmount(expense.amount, locale, expense.currency),
            currency: expense.currency,
          })}
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {t('form.cancel')}
          </Button>
          <Button
            onClick={handleDelete}
            disabled={deleting}
            variant="destructive"
            className="whitespace-nowrap"
          >
            {deleting ? t('delete.deleting') : t('delete.confirmButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
