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
  createInstallment,
  updateInstallment,
} from '@/app/(protected)/installments/installment-actions';
import {
  buildInstallmentFormSchema,
  type InstallmentFormValues,
} from '@/app/(protected)/installments/installment-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment } from '@/lib/api/installments';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { blockNegativeNumberKeys } from '@/lib/utils/form-events';

interface InstallmentFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  installment?: Installment;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

export function InstallmentFormDialog({
  open,
  onOpenChange,
  installment,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: InstallmentFormDialogProps) {
  const t = useTranslations('installments');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () =>
      buildInstallmentFormSchema(tCommon('form.errors.required'), t('form.invalidPositiveInteger')),
    [t, tCommon],
  );

  const form = useForm<InstallmentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      totalAmount: '',
      installmentAmount: '',
      currency: '',
      installmentsCount: '',
      currentInstallment: '1',
      startDate: '',
      paymentMethod: undefined,
      creditCardId: undefined,
    },
  });

  const isEdit = !!installment;
  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  // Reset form when dialog opens or installment changes.
  useEffect(() => {
    if (open) {
      form.reset({
        name: installment?.name ?? '',
        totalAmount: installment?.totalAmount ? String(Number(installment.totalAmount)) : '',
        installmentAmount: installment?.installmentAmount
          ? String(Number(installment.installmentAmount))
          : '',
        currency: installment?.currency ?? '',
        installmentsCount: installment ? String(installment.installmentsCount) : '',
        currentInstallment: installment ? String(installment.currentInstallment) : '1',
        startDate: installment?.startDate ?? '',
        paymentMethod: (installment?.paymentMethod ??
          undefined) as InstallmentFormValues['paymentMethod'],
        creditCardId: installment?.creditCardId ?? undefined,
      });
    }
  }, [open, installment, form]);

  // Clear credit card when payment method changes away from credit_card.
  useEffect(() => {
    if (watchedPaymentMethod !== 'credit_card' && form.getValues('creditCardId')) {
      form.setValue('creditCardId', undefined);
    }
  }, [watchedPaymentMethod, form]);

  async function onSubmit(values: InstallmentFormValues) {
    try {
      if (isEdit) {
        await updateInstallment(installment.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createInstallment(values);
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
            id="installment-form"
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
                name="totalAmount"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.totalAmount.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        step="0.01"
                        min="0"
                        onKeyDown={blockNegativeNumberKeys}
                        placeholder={t('form.totalAmount.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="installmentAmount"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.installmentAmount.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        step="0.01"
                        min="0"
                        onKeyDown={blockNegativeNumberKeys}
                        placeholder={t('form.installmentAmount.placeholder')}
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
                name="installmentsCount"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.installmentsCount.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        inputMode="numeric"
                        placeholder={t('form.installmentsCount.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="currentInstallment"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.currentInstallment.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        inputMode="numeric"
                        placeholder={t('form.currentInstallment.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="startDate"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.startDate.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.startDate.placeholder')}
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
          <Button blue type="submit" form="installment-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
