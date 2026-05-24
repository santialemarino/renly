'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import { deleteReconciliation } from '@/app/(protected)/credit-cards/credit-card-actions';
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

  // Preserve reconciliation data during close animation.
  const lastRec = useRef(reconciliation);
  if (reconciliation) lastRec.current = reconciliation;

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('delete.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">{t('delete.confirm')}</p>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {tForm('cancel')}
          </Button>
          <Button
            onClick={handleDelete}
            disabled={deleting}
            variant="destructive"
            className="whitespace-nowrap"
          >
            {deleting ? t('delete.deleting') : t('delete.confirmButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
