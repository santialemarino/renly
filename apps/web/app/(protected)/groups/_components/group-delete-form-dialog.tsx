'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteGroup } from '@/app/(protected)/groups/groups-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
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
    <TypeToConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      entity={group}
      title={t('delete.title')}
      description={(g) => t('delete.description', { name: g.name, count: g.investmentIds.length })}
      confirmName={(g) => g.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirm')}
    />
  );
}
