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
import { deleteGroup } from '@/app/(protected)/groups/groups-actions';
import type { InvestmentGroup } from '@/lib/api/groups';

interface GroupDeleteFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: InvestmentGroup;
  onSuccess: () => void;
}

export function GroupDeleteFormDialog({
  open,
  onOpenChange,
  group,
  onSuccess,
}: GroupDeleteFormDialogProps) {
  const t = useTranslations('groups');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteGroup(group.id);
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
          {t('delete.description', { name: group.name, count: group.investmentIds.length })}
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {t('delete.cancel')}
          </Button>
          <Button
            onClick={handleDelete}
            disabled={deleting}
            className="whitespace-nowrap bg-red-500 text-white hover:bg-red-600 active:bg-red-700"
          >
            {deleting ? t('delete.deleting') : t('delete.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
