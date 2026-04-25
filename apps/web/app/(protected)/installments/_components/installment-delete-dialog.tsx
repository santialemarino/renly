'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteInstallment } from '@/app/(protected)/installments/installment-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { Installment } from '@/lib/api/installments';

interface InstallmentDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  installment: Installment | null;
  onSuccess: () => void;
}

export function InstallmentDeleteDialog({
  open,
  onOpenChange,
  installment,
  onSuccess,
}: InstallmentDeleteDialogProps) {
  const t = useTranslations('installments');
  const [deleting, setDeleting] = useState(false);

  // Preserve installment data during close animation so the name doesn't disappear.
  const lastInstallment = useRef(installment);
  if (installment) lastInstallment.current = installment;
  const display = installment ?? lastInstallment.current;

  async function handleDelete() {
    if (!installment) return;
    setDeleting(true);
    try {
      await deleteInstallment(installment.id);
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
      title={t('delete.title')}
      description={t('delete.confirm', { name: display?.name ?? '' })}
      confirmName={display?.name ?? ''}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
    />
  );
}
