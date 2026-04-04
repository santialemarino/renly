'use client';

import { useState } from 'react';
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
import { deleteCreditCard } from '@/app/(protected)/credit-cards/credit-card-actions';
import type { CreditCard } from '@/lib/api/credit-cards';

interface CreditCardDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  card: CreditCard;
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
    setDeleting(true);
    try {
      await deleteCreditCard(card.id);
      toast.success(t('delete.success'));
      onOpenChange(false);
      onSuccess();
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
        <p className="text-paragraph-sm text-muted-foreground">
          {t('delete.confirm', { name: card.name })}
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
            variant="destructive"
            className="whitespace-nowrap"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? t('delete.deleting') : t('delete.confirmButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
