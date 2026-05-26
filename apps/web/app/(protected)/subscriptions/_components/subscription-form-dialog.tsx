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
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import {
  createSubscription,
  updateSubscription,
} from '@/app/(protected)/subscriptions/subscription-actions';
import {
  buildSubscriptionFormSchema,
  type SubscriptionFormValues,
} from '@/app/(protected)/subscriptions/subscription-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Subscription } from '@/lib/api/subscriptions';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { BILLING_CYCLES } from '@/lib/constants/recurrences';

interface SubscriptionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subscription?: Subscription;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

export function SubscriptionFormDialog({
  open,
  onOpenChange,
  subscription,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: SubscriptionFormDialogProps) {
  const t = useTranslations('subscriptions');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildSubscriptionFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<SubscriptionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      amount: '',
      currency: '',
      billingCycle: 'monthly',
      nextBillingDate: '',
      paymentMethod: undefined,
      creditCardId: undefined,
    },
  });

  const isEdit = !!subscription;
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  // Reset form when dialog opens or subscription changes.
  useEffect(() => {
    if (open) {
      form.reset({
        name: subscription?.name ?? '',
        amount: subscription?.amount ? String(Number(subscription.amount)) : '',
        currency: subscription?.currency ?? '',
        billingCycle:
          (subscription?.billingCycle as SubscriptionFormValues['billingCycle']) ?? 'monthly',
        nextBillingDate: subscription?.nextBillingDate ?? '',
        paymentMethod: (subscription?.paymentMethod ??
          undefined) as SubscriptionFormValues['paymentMethod'],
        creditCardId: subscription?.creditCardId ?? undefined,
      });
    }
  }, [open, subscription, form]);

  // Clear credit card when payment method changes away from credit_card.
  useEffect(() => {
    if (watchedPaymentMethod !== 'credit_card' && form.getValues('creditCardId')) {
      form.setValue('creditCardId', undefined);
    }
  }, [watchedPaymentMethod, form]);

  async function onSubmit(values: SubscriptionFormValues) {
    try {
      if (isEdit) {
        await updateSubscription(subscription.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createSubscription(values);
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
            id="subscription-form"
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
                      <LocaleAmountInput {...field} placeholder={t('form.amount.placeholder')} />
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
                name="billingCycle"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.billingCycle.label')}</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.billingCycle.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {BILLING_CYCLES.map((cycle) => (
                          <SelectItem key={cycle} value={cycle}>
                            {t(`billingCycles.${cycle}`)}
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
                name="nextBillingDate"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.nextBillingDate.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.nextBillingDate.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button
            blue
            type="submit"
            form="subscription-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
