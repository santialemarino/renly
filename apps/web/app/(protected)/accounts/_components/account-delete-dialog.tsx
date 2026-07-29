'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteAccount } from '@/app/(protected)/accounts/account-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import type { Account } from '@/lib/api/accounts';

interface AccountDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: Account | null;
  onSuccess: () => void;
}

export function AccountDeleteDialog({
  open,
  onOpenChange,
  account,
  onSuccess,
}: AccountDeleteDialogProps) {
  const t = useTranslations('accounts');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!account) return;
    setDeleting(true);
    try {
      await deleteAccount(account.id);
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
      entity={account}
      title={t('delete.title')}
      description={(a) => t('delete.confirm', { name: a.name })}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
      cancelLabel={t('form.cancel')}
    />
  );
}
