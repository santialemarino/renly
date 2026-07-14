'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteSettlement } from '@/app/(protected)/credit-cards/credit-card-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { formatAmount } from '@/lib/utils/currency';

interface SettlementDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  settlement: { id: number; amount: string; currency: string } | null;
  onSuccess: () => void;
}

export function SettlementDeleteDialog({
  open,
  onOpenChange,
  cardId,
  settlement,
  onSuccess,
}: SettlementDeleteDialogProps) {
  const locale = useLocale();
  const t = useTranslations('creditCards');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!settlement) return;
    setDeleting(true);
    try {
      await deleteSettlement(cardId, settlement.id);
      toast.success(t('settlements.deleteSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('settlements.deleteError'));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={settlement}
      title={t('settlements.delete.title')}
      description={(s) =>
        t('settlements.delete.confirm', {
          amount: formatAmount(s.amount, locale, s.currency),
          currency: s.currency,
        })
      }
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('settlements.delete.deleting')}
      confirmLabel={t('settlements.delete.confirmButton')}
      cancelLabel={t('form.cancel')}
    />
  );
}
