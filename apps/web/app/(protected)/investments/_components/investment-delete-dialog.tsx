'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteInvestment } from '@/app/(protected)/investments/investments-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { Investment } from '@/lib/api/investments';

interface InvestmentDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investment: Investment;
  onSuccess: () => void;
}

export function InvestmentDeleteDialog({
  open,
  onOpenChange,
  investment,
  onSuccess,
}: InvestmentDeleteDialogProps) {
  const t = useTranslations('investments');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      const result = await deleteInvestment(investment.id);
      if (!result.ok) {
        toast.error(result.conflictDetail);
        return;
      }
      toast.success(t('delete.success'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('delete.error'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <TypeToConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={investment}
      title={t('delete.title')}
      description={(i) => t('delete.confirm', { name: i.name })}
      confirmName={(i) => i.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
    />
  );
}
