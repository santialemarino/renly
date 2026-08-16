'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
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
import { AccountField } from '@/components/account-field';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { PaymentMethodFields } from '@/components/payment-method-fields';
import type { Account } from '@/lib/api/accounts';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Subscription } from '@/lib/api/subscriptions';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { BILLING_CYCLES } from '@/lib/constants/recurrences';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface SubscriptionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subscription?: Subscription;
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
  // Accounts the optional default funding account can be picked from.
  accounts?: Account[];
  onSuccess: () => void;
}

export function SubscriptionFormDialog({
  open,
  onOpenChange,
  subscription,
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
  accounts,
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
      defaultAccountId: null,
    },
  });

  const isEdit = !!subscription;
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: subscription,
    toValues: (s) => ({
      name: s?.name ?? '',
      amount: s?.amount ? String(Number(s.amount)) : '',
      currency: s?.currency ?? '',
      billingCycle: (s?.billingCycle as SubscriptionFormValues['billingCycle']) ?? 'monthly',
      nextBillingDate: s?.nextBillingDate ?? '',
      paymentMethod: (s?.paymentMethod ?? undefined) as SubscriptionFormValues['paymentMethod'],
      creditCardId: s?.creditCardId ?? undefined,
      defaultAccountId: s?.defaultAccountId ?? null,
    }),
    onSuccess,
  });

  async function onSubmit(values: SubscriptionFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updateSubscription(subscription.id, values) : createSubscription(values)),
      t(isEdit ? 'form.updateSuccess' : 'form.createSuccess'),
      t('form.saveError'),
    );
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
                <FormItem required>
                  <FormLabel>{t('form.name.label')}</FormLabel>
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
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.amount.label')}</FormLabel>
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

              <FormField
                control={form.control}
                name="currency"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('form.currency.label')}</FormLabel>
                    <FormControl>
                      <CurrencyCombobox
                        compact
                        value={field.value || null}
                        exclude={[]}
                        preferredCurrencies={preferredCurrencies}
                        codes={supportedCurrencies}
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
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.billingCycle.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value}
                        onValueChange={field.onChange}
                        placeholder={t('form.billingCycle.placeholder')}
                        options={BILLING_CYCLES.map((cycle) => ({
                          value: cycle,
                          label: t(`billingCycles.${cycle}`),
                        }))}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="nextBillingDate"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.nextBillingDate.label')}</FormLabel>
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

            <PaymentMethodFields
              control={form.control}
              setValue={form.setValue}
              creditCards={creditCards}
              preferredCurrencies={preferredCurrencies}
            />

            {/* A card-paid subscription hits the card and draws cash at the settlement, so it names no
                funding account — the card's own default covers that half. */}
            {/* Height-reveal on the same trigger PaymentMethodFields' card row uses, so the two
                conditional rows in this form animate alike instead of one snapping. */}
            <AnimatePresence initial={false}>
              {watchedPaymentMethod !== 'credit_card' && (
                <motion.div
                  key="default-account"
                  initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                  exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  transition={{ duration: ANIMATION_DEFAULT }}
                >
                  <AccountField
                    control={form.control}
                    setValue={form.setValue}
                    accounts={accounts ?? []}
                    currency={watchedCurrency || undefined}
                    label={t('form.defaultAccount.label')}
                    hint={t('form.defaultAccount.hint')}
                    name="defaultAccountId"
                  />
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
