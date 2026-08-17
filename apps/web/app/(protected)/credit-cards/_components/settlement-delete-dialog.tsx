'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteSettlement } from '@/app/(protected)/credit-cards/credit-card-actions';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { useFormatters } from '@/lib/i18n/formatters';

interface SettlementDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  /*
   * The two legs, because deleting a cross-currency settlement undoes BOTH: the card leg it cleared and
   * the (larger, differently-denominated) cash leg that returns to the funding account. Naming only the
   * card leg understated a real ARS restoration by ~1300x.
   */
  settlement: {
    id: number;
    amount: string;
    currency: string;
    accountAmount: string | null;
    accountCurrency: string | null;
  } | null;
  onSuccess: () => void;
}

export function SettlementDeleteDialog({
  open,
  onOpenChange,
  cardId,
  settlement,
  onSuccess,
}: SettlementDeleteDialogProps) {
  const fmt = useFormatters();
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
        s.accountAmount && s.accountCurrency
          ? t('settlements.delete.confirmCrossCurrency', {
              amount: fmt.amount(s.amount, s.currency),
              currency: s.currency,
              accountAmount: fmt.amount(s.accountAmount, s.accountCurrency),
              accountCurrency: s.accountCurrency,
            })
          : t('settlements.delete.confirm', {
              amount: fmt.amount(s.amount, s.currency),
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
