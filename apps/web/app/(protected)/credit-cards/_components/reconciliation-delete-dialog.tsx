'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteReconciliation } from '@/app/(protected)/credit-cards/credit-card-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { CardReconciliation } from '@/lib/api/card-reconciliations';

interface ReconciliationDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  reconciliation: CardReconciliation | null;
  onSuccess: () => void;
}

export function ReconciliationDeleteDialog({
  open,
  onOpenChange,
  cardId,
  reconciliation,
  onSuccess,
}: ReconciliationDeleteDialogProps) {
  const t = useTranslations('creditCards.reconciliations');
  const tForm = useTranslations('creditCards.form');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!reconciliation) return;
    setDeleting(true);
    try {
      await deleteReconciliation(cardId, reconciliation.id);
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
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={reconciliation}
      title={t('delete.title')}
      description={() => t('delete.confirm')}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
      cancelLabel={tForm('cancel')}
    />
  );
}
