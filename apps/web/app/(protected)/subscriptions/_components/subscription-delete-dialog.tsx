'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { deleteSubscription } from '@/app/(protected)/subscriptions/subscription-actions';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { Subscription } from '@/lib/api/subscriptions';

interface SubscriptionDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subscription: Subscription | null;
  onSuccess: () => void;
}

export function SubscriptionDeleteDialog({
  open,
  onOpenChange,
  subscription,
  onSuccess,
}: SubscriptionDeleteDialogProps) {
  const t = useTranslations('subscriptions');
  const [deleting, setDeleting] = useState(false);

  // Preserve subscription data during close animation so the name doesn't disappear.
  const lastSubscription = useRef(subscription);
  if (subscription) lastSubscription.current = subscription;
  const display = subscription ?? lastSubscription.current;

  async function handleDelete() {
    if (!subscription) return;
    setDeleting(true);
    try {
      await deleteSubscription(subscription.id);
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
      title={t('delete.title')}
      description={t('delete.confirm', { name: display?.name ?? '' })}
      confirmName={display?.name ?? ''}
      onConfirm={handleDelete}
      loading={deleting}
      loadingLabel={t('delete.deleting')}
      confirmLabel={t('delete.confirmButton')}
    />
  );
}
