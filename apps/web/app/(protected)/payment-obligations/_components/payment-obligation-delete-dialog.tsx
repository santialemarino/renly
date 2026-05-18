'use client';

import { useRef, useState } from 'react';
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

  // Preserve obligation data during close animation so the name doesn't disappear.
  const lastObligation = useRef(obligation);
  if (obligation) lastObligation.current = obligation;
  const display = obligation ?? lastObligation.current;

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
