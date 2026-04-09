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
import { archiveCreditCard } from '@/app/(protected)/credit-cards/credit-card-actions';
import type { CreditCard } from '@/lib/api/credit-cards';

interface CreditCardArchiveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  card: CreditCard | null;
  onSuccess: () => void;
}

export function CreditCardArchiveDialog({
  open,
  onOpenChange,
  card,
  onSuccess,
}: CreditCardArchiveDialogProps) {
  const t = useTranslations('creditCards');
  const [archiving, setArchiving] = useState(false);

  // Preserve card data during close animation so the name doesn't disappear.
  const lastCard = useRef(card);
  if (card) lastCard.current = card;
  const displayCard = card ?? lastCard.current;

  async function handleArchive() {
    if (!card) return;
    setArchiving(true);
    try {
      await archiveCreditCard(card.id);
      toast.success(t('archive.success'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('archive.error'));
    } finally {
      setArchiving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('archive.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">
          {t('archive.confirm', { name: displayCard?.name ?? '' })}
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
            onClick={handleArchive}
            disabled={archiving}
          >
            {archiving ? t('archive.cta.loading') : t('archive.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
