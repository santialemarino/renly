'use client';

import { useEffect, useMemo } from 'react';
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
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
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
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { PillToggleGroup } from '@/components/pill-toggle-group';
import { InfoHint } from '@/components/styled-hint';
import type { CreditCard } from '@/lib/api/credit-cards';
import type { Installment } from '@/lib/api/installments';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { PAYMENT_METHODS } from '@/lib/constants/categories';
import { INTEREST_EPSILON } from '@/lib/constants/installments';
import { formatAmount } from '@/lib/utils/currency';

interface InstallmentFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  installment?: Installment;
  preferredCurrencies?: string[];
  creditCards?: CreditCard[];
  onSuccess: () => void;
}

// Derive whether the existing installment plan was registered with interest.
function deriveHasInterest(installment: Installment | undefined): boolean {
  if (!installment) return false;
  const installmentNum = Number(installment.installmentAmount);
  const totalNum = Number(installment.totalAmount);
  const countNum = installment.installmentsCount;
  if (!Number.isFinite(installmentNum) || !Number.isFinite(totalNum) || !countNum) return false;
  return installmentNum * countNum > totalNum + INTEREST_EPSILON;
}

export function InstallmentFormDialog({
  open,
  onOpenChange,
  installment,
  preferredCurrencies,
  creditCards,
  onSuccess,
}: InstallmentFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('installments');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () =>
      buildInstallmentFormSchema({
        requiredMsg: tCommon('form.errors.required'),
        invalidCountMsg: t('form.invalidPositiveInteger'),
        interestMustBePositiveMsg: t('form.interestMustBePositive'),
      }),
    [t, tCommon],
  );

  const form = useForm<InstallmentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      hasInterest: false,
      originalPrice: '',
      installmentAmount: '',
      currency: '',
      installmentsCount: '',
      currentInstallment: '1',
      startDate: '',
      paymentMethod: undefined,
      creditCardId: undefined,
    },
  });

  const watchedPaymentMethod = useWatch({ control: form.control, name: 'paymentMethod' });
  const watchedHasInterest = useWatch({ control: form.control, name: 'hasInterest' });
  const watchedInstallmentAmount = useWatch({ control: form.control, name: 'installmentAmount' });
  const watchedInstallmentsCount = useWatch({ control: form.control, name: 'installmentsCount' });
  const watchedOriginalPrice = useWatch({ control: form.control, name: 'originalPrice' });
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  const isEdit = !!installment;
  const isLocked = isEdit && Number(installment.currentInstallment) > 1;
  const activeCards = creditCards?.filter((c) => c.isActive) ?? [];
  const showCreditCard = watchedPaymentMethod === 'credit_card' && activeCards.length > 0;

  // Derived totals shown below the per-installment row.
  const installmentNum = Number(watchedInstallmentAmount);
  const countNum = Number(watchedInstallmentsCount);
  const hasValidPlan =
    Number.isFinite(installmentNum) &&
    installmentNum > 0 &&
    Number.isFinite(countNum) &&
    countNum >= 1;
  const computedTotalToPay = hasValidPlan ? installmentNum * countNum : null;
  const originalNum = Number(watchedOriginalPrice);
  const computedInterest =
    watchedHasInterest &&
    computedTotalToPay !== null &&
    Number.isFinite(originalNum) &&
    originalNum > 0 &&
    computedTotalToPay > originalNum
      ? computedTotalToPay - originalNum
      : null;
  // Show the derived line only when there's something meaningful to display:
  // No interest just needs a valid total, With interest also needs a positive interest.
  const showDerivedLine =
    computedTotalToPay !== null && (watchedHasInterest ? computedInterest !== null : true);

  // Reset form when dialog opens or installment changes.
  useEffect(() => {
    if (open) {
      const hasInterest = deriveHasInterest(installment);
      form.reset({
        name: installment?.name ?? '',
        hasInterest,
        originalPrice:
          hasInterest && installment?.totalAmount ? String(Number(installment.totalAmount)) : '',
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

  // Clear originalPrice when toggling to No interest so it doesn't linger as form state.
  useEffect(() => {
    if (!watchedHasInterest && form.getValues('originalPrice')) {
      form.setValue('originalPrice', '', { shouldValidate: false });
    }
  }, [watchedHasInterest, form]);

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
            {/* Row 1: name + No/With interest toggle. */}
            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-0">
                    <FormLabel required>{t('form.name.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('form.name.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="hasInterest"
                render={({ field }) => (
                  <FormItem className="shrink-0">
                    <FormLabel>&nbsp;</FormLabel>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div>
                          <PillToggleGroup
                            items={[
                              { value: 'no', label: t('form.interest.noInterest') },
                              { value: 'yes', label: t('form.interest.withInterest') },
                            ]}
                            value={field.value ? 'yes' : 'no'}
                            onValueChange={(v) => field.onChange(v === 'yes')}
                            disabled={isLocked}
                          />
                        </div>
                      </TooltipTrigger>
                      {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                    </Tooltip>
                  </FormItem>
                )}
              />
            </div>

            {/* Row 2 (With interest only): originalPrice + currency, with InfoHint below. */}
            <AnimatePresence initial={false}>
              {watchedHasInterest && (
                <motion.div
                  key="original-price-row"
                  initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                  exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  transition={{ duration: ANIMATION_DEFAULT }}
                  style={{ marginTop: -16 }}
                >
                  <div className="flex flex-col pt-4 gap-y-4">
                    <div className="flex min-w-0 items-start gap-x-3">
                      <FormField
                        control={form.control}
                        name="originalPrice"
                        render={({ field }) => (
                          <FormItem className="flex-1 min-w-0">
                            <FormLabel required>{t('form.originalPrice.label')}</FormLabel>
                            <FormControl>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <LocaleAmountInput
                                    {...field}
                                    placeholder={t('form.originalPrice.placeholder')}
                                    disabled={isLocked}
                                  />
                                </TooltipTrigger>
                                {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                              </Tooltip>
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
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div>
                                    <CurrencyCombobox
                                      compact
                                      value={field.value || null}
                                      exclude={[]}
                                      preferredCurrencies={preferredCurrencies}
                                      disabled={isLocked}
                                      placeholder={t('form.currency.placeholder')}
                                      searchPlaceholder={t('form.currency.searchPlaceholder')}
                                      noResults={t('form.currency.noResults')}
                                      onChange={field.onChange}
                                    />
                                  </div>
                                </TooltipTrigger>
                                {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                              </Tooltip>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <InfoHint>{t('form.interest.noInterestHint')}</InfoHint>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Row 3: installmentAmount + installmentsCount, with derived line below. */}
            <div className="flex flex-col gap-y-2">
              <div className="flex min-w-0 items-start gap-x-3">
                <FormField
                  control={form.control}
                  name="installmentAmount"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel required>{t('form.installmentAmount.label')}</FormLabel>
                      <FormControl>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <LocaleAmountInput
                              {...field}
                              placeholder={t('form.installmentAmount.placeholder')}
                              disabled={isLocked}
                            />
                          </TooltipTrigger>
                          {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                        </Tooltip>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="installmentsCount"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel required>{t('form.installmentsCount.label')}</FormLabel>
                      <FormControl>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Input
                              {...field}
                              inputMode="numeric"
                              placeholder={t('form.installmentsCount.placeholder')}
                              disabled={isLocked}
                            />
                          </TooltipTrigger>
                          {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                        </Tooltip>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Derived totals line. Animated with the same height + opacity +
                  overflow pattern as other conditional rows. The previous "no
                  animation" stance was a workaround for the FormMessage `layout`
                  race fixed in components/form.tsx (popLayout + height-only).
                  We keep a stable key so the wrapper doesn't remount per keystroke
                  — only the text content swaps inside. */}
              <AnimatePresence initial={false}>
                {showDerivedLine && (
                  <motion.div
                    key="derived-totals"
                    initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                    exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    style={{ marginTop: -8 }}
                  >
                    <div className="text-paragraph-xs text-muted-foreground pt-2">
                      {watchedHasInterest && computedInterest !== null ? (
                        <>
                          {t('form.derived.totalToPay', {
                            amount: formatAmount(
                              String(computedTotalToPay),
                              locale,
                              watchedCurrency || undefined,
                            ),
                          })}
                          {' · '}
                          {t('form.derived.interest', {
                            amount: formatAmount(
                              String(computedInterest),
                              locale,
                              watchedCurrency || undefined,
                            ),
                          })}
                        </>
                      ) : (
                        t('form.derived.total', {
                          amount: formatAmount(
                            String(computedTotalToPay),
                            locale,
                            watchedCurrency || undefined,
                          ),
                        })
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Row 4 (No interest only): currency + startDate. */}
            <AnimatePresence initial={false}>
              {!watchedHasInterest && (
                <motion.div
                  key="currency-start-row"
                  initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                  exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  transition={{ duration: ANIMATION_DEFAULT }}
                  style={{ marginTop: -16 }}
                >
                  <div className="flex min-w-0 items-start pt-4 gap-x-3">
                    <FormField
                      control={form.control}
                      name="currency"
                      render={({ field }) => (
                        <FormItem className="flex-1 min-w-0">
                          <FormLabel required>{t('form.currency.label')}</FormLabel>
                          <FormControl>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div>
                                  <CurrencyCombobox
                                    compact
                                    value={field.value || null}
                                    exclude={[]}
                                    preferredCurrencies={preferredCurrencies}
                                    disabled={isLocked}
                                    placeholder={t('form.currency.placeholder')}
                                    searchPlaceholder={t('form.currency.searchPlaceholder')}
                                    noResults={t('form.currency.noResults')}
                                    onChange={field.onChange}
                                  />
                                </div>
                              </TooltipTrigger>
                              {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                            </Tooltip>
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
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div>
                                  <DatePickerInput
                                    value={field.value || undefined}
                                    onChange={field.onChange}
                                    disabled={isLocked}
                                    placeholder={t('form.startDate.placeholder')}
                                  />
                                </div>
                              </TooltipTrigger>
                              {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                            </Tooltip>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Row 4 (With interest only): startDate full-width. */}
            <AnimatePresence initial={false}>
              {watchedHasInterest && (
                <motion.div
                  key="start-row"
                  initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                  exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                  transition={{ duration: ANIMATION_DEFAULT }}
                  style={{ marginTop: -16 }}
                >
                  <div className="pt-4">
                    <FormField
                      control={form.control}
                      name="startDate"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel required>{t('form.startDate.label')}</FormLabel>
                          <FormControl>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div>
                                  <DatePickerInput
                                    value={field.value || undefined}
                                    onChange={field.onChange}
                                    disabled={isLocked}
                                    placeholder={t('form.startDate.placeholder')}
                                  />
                                </div>
                              </TooltipTrigger>
                              {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                            </Tooltip>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Edit-only: currentInstallment full-width with hint. */}
            {isEdit && (
              <div className="flex flex-col gap-y-2">
                <FormField
                  control={form.control}
                  name="currentInstallment"
                  render={({ field }) => (
                    <FormItem>
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
                <p className="text-paragraph-xs text-muted-foreground">
                  {t('form.currentInstallment.editHint')}
                </p>
              </div>
            )}

            {/* Payment method full-width. */}
            <FormField
              control={form.control}
              name="paymentMethod"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.paymentMethod.label')}</FormLabel>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div>
                        <Select
                          value={field.value ?? ''}
                          onValueChange={field.onChange}
                          disabled={isLocked}
                        >
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
                      </div>
                    </TooltipTrigger>
                    {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                  </Tooltip>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Conditional credit card. */}
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div>
                                <Select
                                  value={field.value?.toString() ?? ''}
                                  onValueChange={(v) => field.onChange(Number(v))}
                                  disabled={isLocked}
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
                              </div>
                            </TooltipTrigger>
                            {isLocked && <TooltipContent>{t('form.locked')}</TooltipContent>}
                          </Tooltip>
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
