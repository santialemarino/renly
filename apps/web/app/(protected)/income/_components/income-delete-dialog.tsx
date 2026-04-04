'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import { deleteIncome } from '@/app/(protected)/income/income-actions';
import type { IncomeEntry } from '@/lib/api/income';
import { formatAmount } from '@/lib/utils/currency';

interface IncomeDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  income: IncomeEntry;
  onSuccess: () => void;
}

export function IncomeDeleteDialog({
  open,
  onOpenChange,
  income,
  onSuccess,
}: IncomeDeleteDialogProps) {
  const t = useTranslations('income');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteIncome(income.id);
      toast.success(t('delete.success'));
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
          {t('delete.confirm', { amount: formatAmount(income.amount), currency: income.currency })}
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
