'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteGroup } from '@/app/(protected)/shared/group-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { Group } from '@/lib/api/groups';

interface GroupDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: Group;
  onSuccess: () => void;
}

/*
 * Type-to-confirm rather than a plain confirm, because deleting a group is the widest destructive
 * action in the app: it removes every seat and every outstanding invite with it, for everyone, and the
 * other members get no say. Re-creating the group afterwards does not undo it either — the placeholder
 * seats the group's history hangs off are gone with it.
 */
export function GroupDeleteDialog({
  open,
  onOpenChange,
  group,
  onSuccess,
}: GroupDeleteDialogProps) {
  const t = useTranslations('shared');
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      // A refusal carries its own reason (an admin demoted in another tab), so it is shown instead of
      // the generic failure copy.
      const result = await deleteGroup(group.id);
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
      entity={group}
      title={t('delete.title')}
      description={(g) => t('delete.description', { name: g.name, count: g.activeMemberCount })}
      confirmName={(g) => g.name}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.loading')}
      confirmLabel={t('delete.confirm')}
    />
  );
}
