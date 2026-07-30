'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteIncome } from '@/app/(protected)/income/income-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { IncomeEntry } from '@/lib/api/income';
import { useFormatters } from '@/lib/i18n/formatters';

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
  const fmt = useFormatters();
  const t = useTranslations('income');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      const result = await deleteIncome(income.id);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
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
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={income}
      title={t('delete.title')}
      description={(i) =>
        t('delete.confirm', {
          amount: fmt.amount(i.amount, i.currency),
          currency: i.currency,
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
