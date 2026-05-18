'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { createExpense, updateExpense } from '@/app/(protected)/expenses/expenses-actions';
import {
  buildExpenseFormSchema,
  type ExpenseFormValues,
} from '@/app/(protected)/expenses/expenses-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Expense } from '@/lib/api/expenses';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';
import { blockNegativeNumberKeys } from '@/lib/utils/form-events';

interface ExpenseFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  expense?: Expense;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

export function ExpenseFormDialog({
  open,
  onOpenChange,
  expense,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: ExpenseFormDialogProps) {
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
    },
  });

  const isEdit = !!expense;
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  const sortedCategories = sortExpenseCategoriesByLabel((key) => t(key));

  // Reset form when dialog opens or expense changes.
  useEffect(() => {
    if (open) {
      form.reset({
        date: expense?.date ?? '',
        amount: expense?.amount ? String(Number(expense.amount)) : '',
        currency: expense?.currency ?? '',
        category: (expense?.category ?? undefined) as ExpenseFormValues['category'],
        notes: expense?.notes ?? '',
        paymentMethod: (expense?.paymentMethod ?? undefined) as ExpenseFormValues['paymentMethod'],
        creditCardId: expense?.creditCardId ?? undefined,
      });
    }
  }, [open, expense, form]);

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
      if (isEdit) {
        await updateExpense(expense.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createExpense(values);
        toast.success(t('form.createSuccess'));
      }
      onSuccess();
      onOpenChange(false);
      setNovelCurrencyPending(null);
    } catch {
      toast.error(t('form.saveError'));
    }
  }

  async function onSubmit(values: ExpenseFormValues) {
    if (!isEdit && selectedNovelCurrencyCardName(values)) {
      setNovelCurrencyPending(values);
      return;
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
                        <Input
                          {...field}
                          type="number"
                          step="0.01"
                          min="0"
                          onKeyDown={blockNegativeNumberKeys}
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
              currency: novelCurrencyPending?.currency ?? '',
              cardName: novelCurrencyPending
                ? (selectedNovelCurrencyCardName(novelCurrencyPending) ?? '')
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
    </>
  );
}
