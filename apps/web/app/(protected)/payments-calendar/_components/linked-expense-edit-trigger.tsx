'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { ExpenseFormDialog } from '@/app/(protected)/expenses/_components/expense-form-dialog';
import { getExpenseById } from '@/app/(protected)/expenses/expenses-actions';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense } from '@/lib/api/expenses';

interface LinkedExpenseEditTriggerProps {
  linkedExpenseId: number;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  children: React.ReactNode;
}

// Wraps a Paid-cycle row on the Payments Calendar with a click handler that fetches
// the linked expense by id and opens its edit dialog in-place — no page navigation.
// The expense form is the same dialog used elsewhere; the user can edit, delete, or
// just inspect, then close to return to the calendar.
export function LinkedExpenseEditTrigger({
  linkedExpenseId,
  preferredCurrencies,
  creditCards,
  children,
}: LinkedExpenseEditTriggerProps) {
  const t = useTranslations('paymentsCalendar');
  const router = useRouter();
  const [expense, setExpense] = useState<Expense | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    if (loading || open) return;
    setLoading(true);
    try {
      const fetched = await getExpenseById(linkedExpenseId);
      setExpense(fetched);
      setOpen(true);
    } catch {
      toast.error(t('paidBadge.fetchError'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        disabled={loading}
        className="block w-full disabled:opacity-60 text-left"
        aria-label={t('paidBadge.ariaLabel')}
      >
        {children}
      </button>
      <ExpenseFormDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setExpense(null);
        }}
        expense={expense ?? undefined}
        preferredCurrencies={preferredCurrencies}
        creditCards={creditCards}
        onSuccess={() => router.refresh()}
      />
    </>
  );
}
