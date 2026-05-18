'use client';

import { useEffect, useMemo } from 'react';
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
import {
  createPaymentObligation,
  updatePaymentObligation,
} from '@/app/(protected)/payment-obligations/payment-obligation-actions';
import {
  buildPaymentObligationFormSchema,
  type PaymentObligationFormValues,
} from '@/app/(protected)/payment-obligations/payment-obligation-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { PaymentObligation } from '@/lib/api/payment-obligations';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { OBLIGATION_RECURRENCES } from '@/lib/constants/recurrences';
import { blockNegativeNumberKeys } from '@/lib/utils/form-events';

// Form-internal sentinel for "no recurrence" — the API stores NULL, but a Select
// can't bind to undefined cleanly, so we round-trip through an empty string and
// strip it back to undefined in onSubmit.
const NONE_RECURRENCE = 'none';

interface PaymentObligationFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  obligation?: PaymentObligation;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

export function PaymentObligationFormDialog({
  open,
  onOpenChange,
  obligation,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: PaymentObligationFormDialogProps) {
  const t = useTranslations('paymentObligations');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildPaymentObligationFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<PaymentObligationFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      amount: '',
      currency: '',
      dueDate: '',
      recurrence: undefined,
      category: '',
      paymentMethod: undefined,
      creditCardId: undefined,
      notes: '',
    },
  });

  const isEdit = !!obligation;
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  // Reset form when dialog opens or obligation changes.
  useEffect(() => {
    if (open) {
      form.reset({
        name: obligation?.name ?? '',
        amount: obligation?.amount ? String(Number(obligation.amount)) : '',
        currency: obligation?.currency ?? '',
        dueDate: obligation?.dueDate ?? '',
        recurrence: (obligation?.recurrence ??
          undefined) as PaymentObligationFormValues['recurrence'],
        category: obligation?.category ?? '',
        paymentMethod: (obligation?.paymentMethod ??
          undefined) as PaymentObligationFormValues['paymentMethod'],
        creditCardId: obligation?.creditCardId ?? undefined,
        notes: obligation?.notes ?? '',
      });
    }
  }, [open, obligation, form]);

  // Clear credit card when payment method changes away from credit_card.
  useEffect(() => {
    if (watchedPaymentMethod !== 'credit_card' && form.getValues('creditCardId')) {
      form.setValue('creditCardId', undefined);
    }
  }, [watchedPaymentMethod, form]);

  async function onSubmit(values: PaymentObligationFormValues) {
    try {
      if (isEdit) {
        await updatePaymentObligation(obligation.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createPaymentObligation(values);
        toast.success(t('form.createSuccess'));
      }
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('form.saveError'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('form.titleEdit') : t('form.titleCreate')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="payment-obligation-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel required>{t('form.name.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('form.name.placeholder')} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex min-w-0 items-start gap-x-3">
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
            </div>

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="dueDate"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.dueDate.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.dueDate.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="recurrence"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>{t('form.recurrence.label')}</FormLabel>
                    <Select
                      value={field.value ?? NONE_RECURRENCE}
                      onValueChange={(v) =>
                        field.onChange(
                          v === NONE_RECURRENCE
                            ? undefined
                            : (v as PaymentObligationFormValues['recurrence']),
                        )
                      }
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.recurrence.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE_RECURRENCE}>{t('recurrences.oneOff')}</SelectItem>
                        {OBLIGATION_RECURRENCES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {t(`recurrences.${r}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="category"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.category.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('form.category.placeholder')} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="paymentMethod"
              render={({ field }) => (
                <FormItem>
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

            <AnimatePresence initial={false}>
              {showCreditCard && (
                <motion.div
                  key="credit-card"
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
          <Button
            blue
            type="submit"
            form="payment-obligation-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
