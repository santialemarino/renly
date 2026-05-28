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
import { updatePaymentObligationAmount } from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import { updateSubscriptionAmount } from '@/app/(protected)/subscriptions/subscription-actions';

// Follow-up amount-mismatch prompt fired by ExpenseFormDialog when a manual entry linked
// to an obligation or subscription is saved with an amount differing from the plan's
// current expected amount (Phase 3, follow-up Item 6). Sibling to the form dialog so it
// survives the form's close animation. Reads translations from common.amountMismatch.* so
// the same copy fires whether triggered from /payment-obligations Mark Paid or from a
// manual link on /expenses (consistency was the explicit goal of Item 6).

export interface LinkedPlanMismatch {
  type: 'obligation' | 'subscription';
  planId: number;
  planName: string;
  enteredAmount: string;
  currentAmount: string;
  currency: string;
}

interface LinkedPlanAmountMismatchDialogProps {
  mismatch: LinkedPlanMismatch | null;
  onClose: () => void;
  onConfirmed: () => void;
}

export function LinkedPlanAmountMismatchDialog({
  mismatch,
  onClose,
  onConfirmed,
}: LinkedPlanAmountMismatchDialogProps) {
  // Picks the obligation or subscription sub-namespace based on plan.type; defaults to
  // obligation when no mismatch is set (dialog is closed — the value won't surface).
  const tType = useTranslations(`common.amountMismatch.${mismatch?.type ?? 'obligation'}` as const);
  const [updating, setUpdating] = useState(false);

  async function confirm() {
    if (!mismatch) return;
    setUpdating(true);
    try {
      if (mismatch.type === 'obligation') {
        await updatePaymentObligationAmount(mismatch.planId, mismatch.enteredAmount);
      } else {
        await updateSubscriptionAmount(mismatch.planId, mismatch.enteredAmount);
      }
      toast.success(tType('updateSuccess'));
      onConfirmed();
    } catch {
      toast.error(tType('updateError'));
    } finally {
      setUpdating(false);
    }
  }

  const title = tType('title');
  const description = tType('description', {
    planName: mismatch?.planName ?? '',
    enteredAmount: mismatch?.enteredAmount ?? '',
    currentAmount: mismatch?.currentAmount ?? '',
    currency: mismatch?.currency ?? '',
  });
  const confirmLabel = updating ? tType('updating') : tType('confirm');
  const declineLabel = tType('decline');

  return (
    <Dialog
      open={!!mismatch}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={updating}>
            {declineLabel}
          </Button>
          <Button blue onClick={confirm} disabled={updating}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
