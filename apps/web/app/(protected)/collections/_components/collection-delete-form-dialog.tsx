'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteCollection } from '@/app/(protected)/collections/collections-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { InvestmentCollection } from '@/lib/api/collections';

interface CollectionDeleteFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collection: InvestmentCollection;
  onSuccess: () => void;
}

export function CollectionDeleteFormDialog({
  open,
  onOpenChange,
  collection,
  onSuccess,
}: CollectionDeleteFormDialogProps) {
  const t = useTranslations('collections');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteCollection(collection.id);
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
    <TypeToConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={collection}
      title={t('delete.title')}
      description={(c) => t('delete.description', { name: c.name, count: c.investmentIds.length })}
      confirmName={(c) => c.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirm')}
    />
  );
}
