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
import { archiveInvestment } from '@/app/(protected)/investments/investments-actions';
import type { Investment } from '@/lib/api/investments';

interface InvestmentArchiveFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investment: Investment;
  onSuccess: () => void;
}

export function InvestmentArchiveFormDialog({
  open,
  onOpenChange,
  investment,
  onSuccess,
}: InvestmentArchiveFormDialogProps) {
  const t = useTranslations('investments');
  const [archiving, setArchiving] = useState(false);

  async function handleArchive() {
    setArchiving(true);
    try {
      await archiveInvestment(investment.id);
      toast.success(t('archiveForm.success'));
      onOpenChange(false);
      onSuccess();
    } catch {
      toast.error(t('archiveForm.error'));
    } finally {
      setArchiving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('archiveForm.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">
          {t('archiveForm.confirm', { name: investment.name })}
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
            onClick={handleArchive}
            disabled={archiving}
            className="whitespace-nowrap bg-red-500 text-white hover:bg-red-600 active:bg-red-700"
          >
            {archiving ? t('archiveForm.cta.loading') : t('archiveForm.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
