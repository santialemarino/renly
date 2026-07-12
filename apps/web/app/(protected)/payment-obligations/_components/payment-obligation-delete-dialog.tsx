'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deletePaymentObligation } from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { PaymentObligation } from '@/lib/api/payment-obligations';

interface PaymentObligationDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  obligation: PaymentObligation | null;
  onSuccess: () => void;
}

export function PaymentObligationDeleteDialog({
  open,
  onOpenChange,
  obligation,
  onSuccess,
}: PaymentObligationDeleteDialogProps) {
  const t = useTranslations('paymentObligations');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!obligation) return;
    setDeleting(true);
    try {
      await deletePaymentObligation(obligation.id);
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
      entity={obligation}
      title={t('delete.title')}
      description={(o) => t('delete.confirm', { name: o.name })}
      confirmName={(o) => o.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
    />
  );
}
