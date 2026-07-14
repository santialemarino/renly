'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteCreditCard } from '@/app/(protected)/credit-cards/credit-card-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { CreditCard } from '@/lib/api/credit-cards';

interface CreditCardDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  card: CreditCard | null;
  onSuccess: () => void;
}

export function CreditCardDeleteDialog({
  open,
  onOpenChange,
  card,
  onSuccess,
}: CreditCardDeleteDialogProps) {
  const t = useTranslations('creditCards');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!card) return;
    setDeleting(true);
    try {
      const result = await deleteCreditCard(card.id);
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
      entity={card}
      title={t('delete.title')}
      description={(c) => t('delete.confirm', { name: c.name })}
      confirmName={(c) => c.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
    />
  );
}
