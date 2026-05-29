'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
import { useLocale, useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { resolveCursorToast } from '@/app/(protected)/expenses/_components/cursor-toast';
import {
  LinkedObligationSelect,
  obligationMatchStatus,
} from '@/app/(protected)/expenses/_components/linked-obligation-select';
import {
  LinkedSubInstallmentSelect,
  subInstallmentMatchStatus,
  type LinkedSubInstallmentValue,
} from '@/app/(protected)/expenses/_components/linked-sub-installment-select';
import {
  createExpense,
  getAutoChargeMatch,
  getCycleAdvancePreview,
  updateExpense,
  type AutoChargeMatch,
  type CycleAdvancePreview,
  type ExpenseMutationOutcome,
} from '@/app/(protected)/expenses/expenses-actions';
import { ExpenseConflictError } from '@/app/(protected)/expenses/expenses-errors';
import {
  buildExpenseFormSchema,
  type ExpenseFormValues,
} from '@/app/(protected)/expenses/expenses-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense } from '@/lib/api/expenses';
import type { Installment } from '@/lib/api/installments';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import type { Subscription } from '@/lib/api/subscriptions';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';
import { formatDateForLocale } from '@/lib/utils/format';

// Pre-fill payload passed by the obligations table "Mark paid" action (Phase 3, Step E).
// When supplied (and `expense` is absent), the form opens in CREATE mode with values
// copied from the obligation and the FK set so the server auto-advances on save.
export interface PrefillFromObligation {
  amount: string;
  currency: string;
  paymentMethod?: ExpenseFormValues['paymentMethod'];
  creditCardId?: number;
  category?: ExpenseFormValues['category'];
  paymentObligationId: number;
}

interface ExpenseFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  expense?: Expense;
  prefillFromObligation?: PrefillFromObligation;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  activeObligations?: PaymentObligation[];
  activeSubscriptions?: Subscription[];
  activeInstallments?: Installment[];
  onSuccess: () => void;
  // Optional post-save hook for the amount-mismatch follow-up prompt (Phase 3, follow-up
  // Item 6). Fires AFTER a successful save and BEFORE the form closes — the parent's
  // dialog can mount as a sibling and survive the form's close animation. The dialog
  // computes the mismatch internally and only fires the callback when (a) the saved
  // amount differs from the linked plan's current amount by more than AMOUNT_TOLERANCE
  // AND (b) the entry's currency matches the plan's currency (cross-currency comparison
  // would be semantically muddled — the prompt is about updating the plan's expected
  // amount, which only makes sense in the plan's own currency). Installments are
  // deliberately excluded: their per-cuota drift is taxes/fees/FX rather than plan
  // changes, and LOCKED_FIELDS in installment_service forbids amount edits after
  // current_installment > 1.
  onLinkedPlanSave?: (
    savedValues: ExpenseFormValues,
    plan: {
      type: 'obligation' | 'subscription';
      id: number;
      name: string;
      amount: string;
      currency: string;
    },
  ) => void;
}

// Tolerance for the amount-mismatch prompt — anything within 0.01 currency unit is
// treated as equal (avoids prompting on rounding noise from string-to-number conversion).
const AMOUNT_TOLERANCE = 0.01;

// Resolves the linked plan (obligation or subscription) from the saved form values,
// looking it up in the active plans the parent prop-drilled. Returns null when no FK
// is set or the looked-up plan can't be found (e.g. user picked a plan that's since been
// archived — should be rare since active lists are server-fetched fresh per render).
function detectLinkedPlan(
  values: ExpenseFormValues,
  activeObligations: PaymentObligation[] | undefined,
  activeSubscriptions: Subscription[] | undefined,
): {
  type: 'obligation' | 'subscription';
  id: number;
  name: string;
  amount: string;
  currency: string;
} | null {
  if (values.paymentObligationId) {
    const o = activeObligations?.find((x) => x.id === values.paymentObligationId);
    if (o)
      return { type: 'obligation', id: o.id, name: o.name, amount: o.amount, currency: o.currency };
  }
  if (values.subscriptionId) {
    const s = activeSubscriptions?.find((x) => x.id === values.subscriptionId);
    if (s)
      return {
        type: 'subscription',
        id: s.id,
        name: s.name,
        amount: s.amount,
        currency: s.currency,
      };
  }
  return null;
}

// Compares two amount strings with the standard tolerance. Returns true when the saved
// amount differs from the plan's expected amount by more than AMOUNT_TOLERANCE. Non-finite
// inputs are treated as "no mismatch" — invalid form state shouldn't trigger the prompt.
function amountsDiffer(savedAmount: string, planAmount: string): boolean {
  const entered = Number(savedAmount);
  const current = Number(planAmount);
  if (!Number.isFinite(entered) || !Number.isFinite(current)) return false;
  return Math.abs(entered - current) > AMOUNT_TOLERANCE;
}

export function ExpenseFormDialog({
  open,
  onOpenChange,
  expense,
  prefillFromObligation,
  preferredCurrencies,
  creditCards,
  activeObligations,
  activeSubscriptions,
  activeInstallments,
  onSuccess,
  onLinkedPlanSave,
}: ExpenseFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildExpenseFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<ExpenseFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      currency: '',
      category: undefined,
      notes: '',
      paymentMethod: undefined,
      creditCardId: undefined,
      paymentObligationId: undefined,
      subscriptionId: undefined,
      installmentId: undefined,
    },
  });

  const isEdit = !!expense;
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });
  const watchedCreditCardId = useWatch({ control: form.control, name: 'creditCardId' });
  const watchedPaymentObligationId = useWatch({
    control: form.control,
    name: 'paymentObligationId',
  });
  const watchedSubscriptionId = useWatch({ control: form.control, name: 'subscriptionId' });
  const watchedInstallmentId = useWatch({ control: form.control, name: 'installmentId' });
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  // Linked-obligation dropdown is offered on CREATE and EDIT (Phase 3, follow-up Item 10).
  // The update endpoint now accepts the FK as a JSON-Merge-Patch field; selecting "None"
  // clears the link and the server reverses the obligation's cursor when this row was the
  // most-recent linked expense.
  const showLinkedObligation = (activeObligations?.length ?? 0) > 0;
  const selectedObligation = activeObligations?.find((o) => o.id === watchedPaymentObligationId);
  // Linked-sub/installment dropdown is offered on CREATE and EDIT (Phase 3, follow-up Item 10),
  // and hidden when the form is opened via Mark Paid — the obligation FK is locked in that
  // flow and the sub/installment dropdown would be mutually exclusive noise.
  const showLinkedSubInstallment =
    !prefillFromObligation &&
    ((activeSubscriptions?.length ?? 0) > 0 || (activeInstallments?.length ?? 0) > 0);
  const selectedSubInstallment: LinkedSubInstallmentValue | null =
    watchedSubscriptionId !== undefined
      ? { kind: 'subscription', id: watchedSubscriptionId }
      : watchedInstallmentId !== undefined
        ? { kind: 'installment', id: watchedInstallmentId }
        : null;
  const selectedSubInstallmentPlan: Subscription | Installment | undefined =
    selectedSubInstallment?.kind === 'subscription'
      ? activeSubscriptions?.find((s) => s.id === selectedSubInstallment.id)
      : selectedSubInstallment?.kind === 'installment'
        ? activeInstallments?.find((i) => i.id === selectedSubInstallment.id)
        : undefined;
  const subInstallmentMismatch =
    selectedSubInstallmentPlan !== undefined &&
    subInstallmentMatchStatus(
      selectedSubInstallmentPlan,
      watchedCurrency || undefined,
      watchedPaymentMethod,
      watchedCreditCardId,
    ) === 'mismatch';
  // Mismatch warning fires only on a confirmed conflict ('mismatch' status). 'unknown' (form
  // not fully filled yet) suppresses both the dot and the warning. Shows in both enabled
  // and disabled (Mark Paid) states so the user sees when their edits diverge from the
  // pre-filled obligation's expectations.
  const obligationMismatch =
    selectedObligation !== undefined &&
    obligationMatchStatus(
      selectedObligation,
      watchedCurrency || undefined,
      watchedPaymentMethod,
      watchedCreditCardId,
    ) === 'mismatch';

  const sortedCategories = sortExpenseCategoriesByLabel((key) => t(key), locale);

  // Reset form when dialog opens. Priority: edit expense > obligation pre-fill > empty.
  useEffect(() => {
    if (open) {
      if (expense) {
        form.reset({
          date: expense.date,
          amount: expense.amount ? String(Number(expense.amount)) : '',
          currency: expense.currency ?? '',
          category: (expense.category ?? undefined) as ExpenseFormValues['category'],
          notes: expense.notes ?? '',
          paymentMethod: (expense.paymentMethod ?? undefined) as ExpenseFormValues['paymentMethod'],
          creditCardId: expense.creditCardId ?? undefined,
          paymentObligationId: expense.paymentObligationId ?? undefined,
          subscriptionId: expense.subscriptionId ?? undefined,
          installmentId: expense.installmentId ?? undefined,
        });
      } else if (prefillFromObligation) {
        form.reset({
          date: '',
          amount: String(Number(prefillFromObligation.amount)),
          currency: prefillFromObligation.currency,
          category: prefillFromObligation.category,
          notes: '',
          paymentMethod: prefillFromObligation.paymentMethod,
          creditCardId: prefillFromObligation.creditCardId,
          paymentObligationId: prefillFromObligation.paymentObligationId,
          subscriptionId: undefined,
          installmentId: undefined,
        });
      } else {
        form.reset({
          date: '',
          amount: '',
          currency: '',
          category: undefined,
          notes: '',
          paymentMethod: undefined,
          creditCardId: undefined,
          paymentObligationId: undefined,
          subscriptionId: undefined,
          installmentId: undefined,
        });
      }
    }
  }, [open, expense, prefillFromObligation, form]);

  // Clear credit card when payment method changes away from credit_card.
  useEffect(() => {
    if (watchedPaymentMethod !== 'credit_card' && form.getValues('creditCardId')) {
      form.setValue('creditCardId', undefined);
    }
  }, [watchedPaymentMethod, form]);

  // Soft confirmation when a credit-card expense uses a currency the card
  // hasn't seen before. Catches typos that would otherwise create a phantom
  // bucket. Edits skip the check — the bucket already exists by definition.
  const [novelCurrencyPending, setNovelCurrencyPending] = useState<ExpenseFormValues | null>(null);

  // Soft confirmation when the candidate entry matches a scheduler-generated expense
  // within DUPE_MATCH_WINDOW_DAYS on card / currency / exact amount (Phase 3, Step D).
  // Fires on BOTH create and edit (edit excludes the row being modified so it can't
  // match itself).
  const [autoChargeMatch, setAutoChargeMatch] = useState<{
    values: ExpenseFormValues;
    match: AutoChargeMatch;
  } | null>(null);

  // Soft confirmation when a manual entry linked to a subscription / installment is far
  // enough from the closest expected cycle that the cursor will NOT advance (Phase 3,
  // follow-up 3b). Fires only on CREATE — edit doesn't trigger advance per Item 10
  // (only delete / unlink reverses the cursor), so the preview is unnecessary there.
  const [cycleAdvancePending, setCycleAdvancePending] = useState<{
    values: ExpenseFormValues;
    preview: CycleAdvancePreview;
    planName: string;
  } | null>(null);

  // Clear pending soft-confirmations when the form dialog closes. Otherwise a
  // dupe-match lookup that resolves AFTER the user cancels the form would surface
  // a confirmation dialog with no form behind it (race condition on async submit).
  useEffect(() => {
    if (!open) {
      setNovelCurrencyPending(null);
      setAutoChargeMatch(null);
      setCycleAdvancePending(null);
    }
  }, [open]);

  // Preserve the pending values during the close animation so the description
  // text doesn't blank out and shift the modal mid-exit.
  const lastNovelCurrencyPending = useRef(novelCurrencyPending);
  if (novelCurrencyPending) lastNovelCurrencyPending.current = novelCurrencyPending;
  const novelCurrencyDisplay = novelCurrencyPending ?? lastNovelCurrencyPending.current;

  const lastAutoChargeMatch = useRef(autoChargeMatch);
  if (autoChargeMatch) lastAutoChargeMatch.current = autoChargeMatch;
  const autoChargeMatchDisplay = autoChargeMatch ?? lastAutoChargeMatch.current;

  const lastCycleAdvancePending = useRef(cycleAdvancePending);
  if (cycleAdvancePending) lastCycleAdvancePending.current = cycleAdvancePending;
  const cycleAdvanceDisplay = cycleAdvancePending ?? lastCycleAdvancePending.current;

  function selectedNovelCurrencyCardName(values: ExpenseFormValues): string | null {
    if (values.paymentMethod !== 'credit_card') return null;
    if (!values.creditCardId || !values.currency) return null;
    const card = activeCards.find((c) => c.id === values.creditCardId);
    if (!card) return null;
    if (card.balances.some((b) => b.currency === values.currency)) return null;
    return card.name;
  }

  async function doSubmit(values: ExpenseFormValues) {
    try {
      let outcome: ExpenseMutationOutcome;
      if (isEdit) {
        outcome = await updateExpense(expense.id, values);
        announceSave(t('form.updateSuccess'), outcome);
      } else {
        outcome = await createExpense(values);
        announceSave(t('form.createSuccess'), outcome);
      }
      // Amount-mismatch hook (Phase 3, follow-up Item 6). Fires for both create and
      // edit flows whenever the saved amount differs from the linked plan's current
      // expected amount by more than AMOUNT_TOLERANCE. Installments are excluded —
      // see onLinkedPlanSave's prop doc. Fires BEFORE close so the parent can mount
      // a follow-up dialog as a sibling that survives this dialog's close animation.
      if (onLinkedPlanSave) {
        const linkedPlan = detectLinkedPlan(values, activeObligations, activeSubscriptions);
        if (
          linkedPlan &&
          linkedPlan.currency === values.currency &&
          amountsDiffer(values.amount, linkedPlan.amount)
        ) {
          onLinkedPlanSave(values, linkedPlan);
        }
      }
      onSuccess();
      onOpenChange(false);
      setNovelCurrencyPending(null);
      setAutoChargeMatch(null);
      setCycleAdvancePending(null);
    } catch (err) {
      // Surface the backend's 409 detail (Phase 3, follow-up Item 8.2) verbatim — the
      // partial UNIQUE INDEX message ("A charge is already recorded for this subscription
      // on that date.") is more actionable than the generic save-error toast. Other
      // failures fall back to the generic message.
      if (err instanceof ExpenseConflictError) {
        toast.error(err.detail);
      } else {
        toast.error(t('form.saveError'));
      }
    }
  }

  // Composes the success toast with optional cursor-change lines (Phase 3, follow-up
  // Item 7). The symmetric edit model can fire both a reverse (on the OLD plan losing
  // this expense) and an advance (on the NEW plan gaining it) — e.g. a FK swap. We
  // announce reverse first, then advance, so the toast reads in temporal order:
  // "Expense updated. ABL's next due date moved back to Jun 5. ARBA's next due date
  // moved to Jul 10."
  function announceSave(baseMessage: string, outcome: ExpenseMutationOutcome) {
    const lines: string[] = [baseMessage];
    if (outcome.reverse) {
      const r = resolveCursorToast(outcome.reverse, 'reverse', locale);
      if (r) lines.push(t(`form.${r.key}`, r.params));
    }
    if (outcome.advance) {
      const a = resolveCursorToast(outcome.advance, 'advance', locale);
      if (a) lines.push(t(`form.${a.key}`, a.params));
    }
    toast.success(lines.join(' '));
  }

  async function onSubmit(values: ExpenseFormValues) {
    if (!isEdit && selectedNovelCurrencyCardName(values)) {
      setNovelCurrencyPending(values);
      return;
    }
    // Run the dupe-warning on BOTH create and edit (Phase 3, Step D + 6.ii):
    // edit case excludes the row being modified so an auto-tagged expense doesn't
    // match itself. Only fires when the four match-key fields are present and the
    // payment method is credit card. Errors are non-blocking — fall through to save.
    if (
      values.paymentMethod === 'credit_card' &&
      values.creditCardId &&
      values.currency &&
      values.amount &&
      values.date
    ) {
      try {
        const match = await getAutoChargeMatch({
          creditCardId: values.creditCardId,
          currency: values.currency,
          amount: values.amount,
          date: values.date,
          excludeExpenseId: isEdit ? expense.id : undefined,
        });
        if (match) {
          setAutoChargeMatch({ values, match });
          return;
        }
      } catch {
        // Silent fail — better to allow save than block the user on a lookup error.
      }
    }
    // Cycle-advance preview (Phase 3, follow-up 3b). When the user has linked a
    // subscription / installment AND set a date, ask the backend whether saving will
    // advance the plan's cursor. If not, surface a soft-confirm dialog so the user
    // understands the FK is still saved but the schedule stays put. CREATE only —
    // Item 10 lets the dropdowns appear on edit too, but edit never triggers an advance
    // (only delete / unlink reverses), so the preview is unnecessary there.
    if (!isEdit && values.date && (values.subscriptionId || values.installmentId)) {
      try {
        const preview = await getCycleAdvancePreview({
          entryDate: values.date,
          subscriptionId: values.subscriptionId,
          installmentId: values.installmentId,
        });
        if (!preview.wouldAdvance) {
          const planName = values.subscriptionId
            ? (activeSubscriptions?.find((s) => s.id === values.subscriptionId)?.name ?? '')
            : (activeInstallments?.find((i) => i.id === values.installmentId)?.name ?? '');
          setCycleAdvancePending({ values, preview, planName });
          return;
        }
      } catch {
        // Silent fail — better to allow save than block the user on a lookup error.
      }
    }
    await doSubmit(values);
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isEdit ? t('form.titleEdit') : t('form.titleCreate')}</DialogTitle>
          </DialogHeader>

          <Form {...form}>
            <form
              id="expense-form"
              className="flex flex-col min-w-0 gap-y-4"
              onSubmit={form.handleSubmit(onSubmit)}
              noValidate
            >
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel required>{t('form.date.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.date.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex min-w-0 items-start gap-x-3">
                <FormField
                  control={form.control}
                  name="currency"
                  render={({ field }) => (
                    <FormItem className="flex-1 min-w-0">
                      <FormLabel required>{t('form.currency.label')}</FormLabel>
                      <FormControl>
                        <CurrencyCombobox
                          compact
                          value={field.value || null}
                          exclude={[]}
                          preferredCurrencies={preferredCurrencies}
                          placeholder={t('form.currency.placeholder')}
                          searchPlaceholder={t('form.currency.searchPlaceholder')}
                          noResults={t('form.currency.noResults')}
                          onChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="amount"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel required>{t('form.amount.label')}</FormLabel>
                      <FormControl>
                        <LocaleAmountInput
                          {...field}
                          currency={watchedCurrency || undefined}
                          placeholder={t('form.amount.placeholder')}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="flex min-w-0 items-start gap-x-3">
                <FormField
                  control={form.control}
                  name="category"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel>{t('form.category.label')}</FormLabel>
                      <Select value={field.value ?? ''} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder={t('form.category.placeholder')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {sortedCategories.map((cat) => (
                            <SelectItem key={cat} value={cat}>
                              {t(`categories.${cat}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="paymentMethod"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel>{t('form.paymentMethod.label')}</FormLabel>
                      <Select value={field.value ?? ''} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder={t('form.paymentMethod.placeholder')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {PAYMENT_METHODS.map((method) => (
                            <SelectItem key={method} value={method}>
                              {t(`paymentMethods.${method}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <AnimatePresence initial={false}>
                {showCreditCard && (
                  <motion.div
                    key="credit-card"
                    layout
                    initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                    exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    style={{ marginTop: -16 }}
                  >
                    <div className="pt-4">
                      <FormField
                        control={form.control}
                        name="creditCardId"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t('form.creditCard.label')}</FormLabel>
                            <Select
                              value={field.value?.toString() ?? ''}
                              onValueChange={(v) => field.onChange(Number(v))}
                            >
                              <FormControl>
                                <SelectTrigger className="w-full">
                                  <SelectValue placeholder={t('form.creditCard.placeholder')} />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {activeCards.map((card) => (
                                  <SelectItem key={card.id} value={card.id.toString()}>
                                    {card.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {showLinkedObligation && activeObligations && (
                <FormField
                  control={form.control}
                  name="paymentObligationId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('form.linkedObligation.label')}</FormLabel>
                      <FormControl>
                        <LinkedObligationSelect
                          obligations={activeObligations}
                          value={field.value ?? null}
                          disabled={!!prefillFromObligation}
                          formCurrency={watchedCurrency || undefined}
                          formPaymentMethod={watchedPaymentMethod}
                          formCreditCardId={watchedCreditCardId}
                          onChange={(id) => {
                            field.onChange(id ?? undefined);
                            // Mutual exclusivity (Phase 3, follow-up 3a): an expense pays at
                            // most one commitment-type. Picking an obligation clears the
                            // sub/installment selection.
                            if (id !== null) {
                              form.setValue('subscriptionId', undefined);
                              form.setValue('installmentId', undefined);
                            }
                            // Auto-fill expense category from the obligation when the user
                            // hasn't picked one. Doesn't overwrite an explicit choice.
                            if (id !== null) {
                              const o = activeObligations.find((x) => x.id === id);
                              if (o?.expenseCategory && !form.getValues('category')) {
                                form.setValue(
                                  'category',
                                  o.expenseCategory as ExpenseFormValues['category'],
                                );
                              }
                            }
                          }}
                        />
                      </FormControl>
                      {prefillFromObligation && (
                        <p className="text-paragraph-xs text-muted-foreground">
                          {t('form.linkedObligation.lockedFromMarkPaid')}
                        </p>
                      )}
                      <StyledHint variant="warning" show={obligationMismatch}>
                        {t('form.linkedObligation.mismatch')}
                      </StyledHint>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {showLinkedSubInstallment && (
                <FormItem>
                  <FormLabel>{t('form.linkedSubInstallment.label')}</FormLabel>
                  <FormControl>
                    <LinkedSubInstallmentSelect
                      subscriptions={activeSubscriptions ?? []}
                      installments={activeInstallments ?? []}
                      value={selectedSubInstallment}
                      formCurrency={watchedCurrency || undefined}
                      formPaymentMethod={watchedPaymentMethod}
                      formCreditCardId={watchedCreditCardId}
                      onChange={(next) => {
                        // Mutual exclusivity: picking a sub/installment clears the obligation
                        // and the sibling FK on the same row.
                        if (next === null) {
                          form.setValue('subscriptionId', undefined);
                          form.setValue('installmentId', undefined);
                          return;
                        }
                        form.setValue('paymentObligationId', undefined);
                        if (next.kind === 'subscription') {
                          form.setValue('subscriptionId', next.id);
                          form.setValue('installmentId', undefined);
                        } else {
                          form.setValue('installmentId', next.id);
                          form.setValue('subscriptionId', undefined);
                        }
                      }}
                    />
                  </FormControl>
                  <StyledHint variant="warning" show={subInstallmentMismatch}>
                    {t('form.linkedSubInstallment.mismatch')}
                  </StyledHint>
                </FormItem>
              )}

              <FormField
                control={form.control}
                name="notes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('form.notes.label')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} placeholder={t('form.notes.placeholder')} rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </form>
          </Form>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('form.cancel')}
            </Button>
            <Button blue type="submit" form="expense-form" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Sibling of the expense-form Dialog (not nested) so each gets its own
          Radix overlay. The confirm dialog mounts on top with its own backdrop,
          dimming the expense form behind it the same way other modals do. */}
      <Dialog
        open={!!novelCurrencyPending}
        onOpenChange={(open) => !open && setNovelCurrencyPending(null)}
      >
        {/* Narrower than the form (sm:max-w-md vs sm:max-w-xl) so the dimmed
            form peeks out around the edges, giving the stack a depth feel. */}
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('form.novelCurrency.title')}</DialogTitle>
          </DialogHeader>
          <p className="text-paragraph-sm text-muted-foreground">
            {t('form.novelCurrency.description', {
              currency: novelCurrencyDisplay?.currency ?? '',
              cardName: novelCurrencyDisplay
                ? (selectedNovelCurrencyCardName(novelCurrencyDisplay) ?? '')
                : '',
            })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNovelCurrencyPending(null)}>
              {t('form.cancel')}
            </Button>
            <Button
              blue
              onClick={() => novelCurrencyPending && doSubmit(novelCurrencyPending)}
              disabled={form.formState.isSubmitting}
            >
              {t('form.novelCurrency.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Auto-charge match confirmation (Phase 3, Step D). Same sibling pattern
          as novel-currency — fires when the candidate entry matches an existing
          scheduler-generated expense within DUPE_MATCH_WINDOW_DAYS. */}
      <Dialog open={!!autoChargeMatch} onOpenChange={(open) => !open && setAutoChargeMatch(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('form.autoChargeMatch.title')}</DialogTitle>
          </DialogHeader>
          <p className="text-paragraph-sm text-muted-foreground">
            {t('form.autoChargeMatch.description', {
              planName: autoChargeMatchDisplay?.match.sourcePlan.name ?? '',
              existingDate: autoChargeMatchDisplay?.match.date ?? '',
            })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAutoChargeMatch(null)}>
              {t('form.cancel')}
            </Button>
            <Button
              blue
              onClick={() => autoChargeMatch && doSubmit(autoChargeMatch.values)}
              disabled={form.formState.isSubmitting}
            >
              {t('form.autoChargeMatch.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cycle-advance soft-confirm (Phase 3, follow-up 3b). Same sibling pattern as
          novel-currency / auto-charge — fires when the user has linked a subscription
          or installment but the entry's matched cycle isn't the plan's current cursor,
          so the schedule won't advance on save. Copy branches on `multi_jump`: the
          future-cycle case (matched cycle ahead of cursor — pre-pay / mis-click) reads
          differently from the back-dated case (matched cycle behind cursor — already
          emitted by the scheduler). */}
      <Dialog
        open={!!cycleAdvancePending}
        onOpenChange={(open) => !open && setCycleAdvancePending(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('form.cycleAdvance.title')}</DialogTitle>
          </DialogHeader>
          <p className="text-paragraph-sm text-muted-foreground">
            {cycleAdvanceDisplay?.preview.multiJump
              ? t('form.cycleAdvance.descriptionMultiJump', {
                  planName: cycleAdvanceDisplay?.planName ?? '',
                  nextExpectedDate: formatDateForLocale(
                    cycleAdvanceDisplay?.preview.nextExpectedDate ?? '',
                    locale,
                  ),
                })
              : t('form.cycleAdvance.descriptionBackDated', {
                  planName: cycleAdvanceDisplay?.planName ?? '',
                  nextExpectedDate: formatDateForLocale(
                    cycleAdvanceDisplay?.preview.nextExpectedDate ?? '',
                    locale,
                  ),
                })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCycleAdvancePending(null)}>
              {t('form.cancel')}
            </Button>
            <Button
              blue
              onClick={() => cycleAdvancePending && doSubmit(cycleAdvancePending.values)}
              disabled={form.formState.isSubmitting}
            >
              {t('form.cycleAdvance.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
