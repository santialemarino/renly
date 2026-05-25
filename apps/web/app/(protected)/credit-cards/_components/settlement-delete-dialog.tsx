'use client';

import { useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import { deleteSettlement } from '@/app/(protected)/credit-cards/credit-card-actions';
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

  // Preserve settlement data during close animation.
  const lastSettlement = useRef(settlement);
  if (settlement) lastSettlement.current = settlement;
  const displaySettlement = settlement ?? lastSettlement.current;

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settlements.delete.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">
          {t('settlements.delete.confirm', {
            amount: displaySettlement ? formatAmount(displaySettlement.amount, locale) : '',
            currency: displaySettlement?.currency ?? '',
          })}
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {t('form.cancel')}
          </Button>
          <Button
            onClick={handleDelete}
            disabled={deleting}
            variant="destructive"
            className="whitespace-nowrap"
          >
            {deleting ? t('settlements.delete.deleting') : t('settlements.delete.confirmButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
