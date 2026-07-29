'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteAccountReconciliation } from '@/app/(protected)/accounts/account-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { AccountReconciliation } from '@/lib/api/account-reconciliations';

interface AccountReconciliationDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: number;
  reconciliation: AccountReconciliation | null;
  onSuccess: () => void;
}

export function AccountReconciliationDeleteDialog({
  open,
  onOpenChange,
  accountId,
  reconciliation,
  onSuccess,
}: AccountReconciliationDeleteDialogProps) {
  const t = useTranslations('accounts.reconciliations');
  const tForm = useTranslations('accounts.form');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!reconciliation) return;
    setDeleting(true);
    try {
      await deleteAccountReconciliation(accountId, reconciliation.id);
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
