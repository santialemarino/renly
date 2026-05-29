import type { PlanCursorChange } from '@/app/(protected)/expenses/expenses-actions';
import type { Installment } from '@/lib/api/installments';
import { formatDateForLocale } from '@/lib/utils/format';

// Resolves the translation key + parameters for the cursor-change toast line that
// extends the success toast on create / update / delete (Phase 3, follow-up Item 7).
// Direction selects the namespace (`cursorAdvanceToast` vs `cursorReverseToast`);
// plan-specific branches pick the right key. Date values are formatted via the locale
// rather than passed as raw ISO strings so the toast reads naturally to the user.
// Returns null when the cursorChange carries no meaningful payload (defensive — the
// backend only emits advance_change / reverse_change when something moved, but null-safe
// routing here keeps the call sites simple).

export type ToastDirection = 'advance' | 'reverse';

interface CursorToastResolution {
  key: string;
  params: Record<string, string | number>;
}

export function resolveCursorToast(
  cursorChange: PlanCursorChange,
  direction: ToastDirection,
  locale: string,
  activeInstallments?: Installment[],
): CursorToastResolution | null {
  const ns = direction === 'advance' ? 'cursorAdvanceToast' : 'cursorReverseToast';
  const { planType, planName, newCursor, previousCursor } = cursorChange;

  if (planType === 'subscription') {
    // Subscriptions only walk dates back and forth — they never archive on advance
    // or re-activate on reverse, so there's no archive branch here.
    return {
      key: `${ns}.subscription`,
      params: { planName, newCursor: formatDateForLocale(newCursor, locale) },
    };
  }

  if (planType === 'obligation') {
    // Advance: empty newCursor signals one-off Marked Paid (archived).
    // Reverse: empty previousCursor signals re-activation of an archived one-off.
    if (direction === 'advance' && newCursor === '') {
      return { key: `${ns}.obligationArchived`, params: { planName } };
    }
    if (direction === 'reverse' && previousCursor === '') {
      return { key: `${ns}.obligationReactivated`, params: { planName } };
    }
    return {
      key: `${ns}.obligation`,
      params: { planName, newCursor: formatDateForLocale(newCursor, locale) },
    };
  }

  if (planType === 'installment') {
    // Advance: empty newCursor signals plan fully paid (archived).
    // Reverse: empty previousCursor signals re-activation of an archived plan.
    if (direction === 'advance' && newCursor === '') {
      return { key: `${ns}.installmentArchived`, params: { planName } };
    }
    if (direction === 'reverse' && previousCursor === '') {
      return { key: `${ns}.installmentReactivated`, params: { planName } };
    }
    const plan = activeInstallments?.find((i) => i.id === cursorChange.planId);
    const totalCount = plan?.installmentsCount ?? 0;
    return {
      key: `${ns}.installment`,
      params: { planName, newCursor, totalCount },
    };
  }

  return null;
}
