'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { AnimatePresence, LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import {
  createTransaction,
  deleteTransaction,
  fetchPriceForDate,
  updateTransaction,
  upsertSnapshot,
} from '@/app/(protected)/snapshots/snapshots-actions';
import {
  buildSnapshotFormSchema,
  TRANSACTION_TYPES,
  type SnapshotFormValues,
} from '@/app/(protected)/snapshots/snapshots-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { InfoHint, WarningHint } from '@/components/styled-hint';
import type { SnapshotGridCell } from '@/lib/api/snapshots';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

// Minimum time (ms) from fetch start before showing the result.
// Prevents layout flash when the fetch resolves instantly (DB cache hit).
const PRICE_DISPLAY_DELAY_MS = 1000;

interface SnapshotFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investmentId: number;
  investmentName: string;
  baseCurrency: string;
  ticker: string | null;
  category: string;
  cedearRatio: number | null;
  existingDates: string[];
  cell?: SnapshotGridCell;
  onSuccess: () => void;
}

export function SnapshotFormDialog({
  open,
  onOpenChange,
  investmentId,
  investmentName,
  baseCurrency,
  ticker,
  category,
  cedearRatio,
  existingDates,
  cell,
  onSuccess,
}: SnapshotFormDialogProps) {
  const t = useTranslations('snapshots');
  const tCommon = useTranslations('common');
  const isEdit = !!cell;
  const existingTx = cell?.transaction ?? null;

  const existingYearMonths = useMemo(
    () => new Set(existingDates.map((d) => d.slice(0, 7))),
    [existingDates],
  );

  const schema = useMemo(
    () =>
      buildSnapshotFormSchema(
        tCommon('form.errors.required'),
        t('form.date.duplicate'),
        existingYearMonths,
        isEdit,
      ),
    [tCommon, t, existingYearMonths, isEdit],
  );

  const form = useForm<SnapshotFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      value: '',
      quantity: '',
      includeTransaction: false,
      transactionAmount: '',
      transactionQuantity: '',
      transactionType: 'deposit',
    },
  });

  const includeTransaction = form.watch('includeTransaction');
  const watchedDate = form.watch('date');
  const watchedValue = form.watch('value');
  const watchedQuantity = form.watch('quantity');
  const watchedTxAmount = form.watch('transactionAmount');
  const watchedTxQuantity = form.watch('transactionQuantity');

  // Price state.
  const [fetchedPrice, setFetchedPrice] = useState<number | null>(null);
  const [fetchedPriceCurrency, setFetchedPriceCurrency] = useState<string | null>(null);
  const [effectivePrice, setEffectivePrice] = useState<number | null>(null);
  const [priceConverted, setPriceConverted] = useState(false);
  const [priceLoading, setPriceLoading] = useState(false);
  const [priceFetched, setPriceFetched] = useState(false);
  const [quantityMode, setQuantityMode] = useState(false);

  // True when the snapshot being created would be the earliest for this investment.
  const isEarliestSnapshot = useMemo(() => {
    if (isEdit || !watchedDate) return false;
    if (existingDates.length === 0) return true;
    return existingDates.every((d) => watchedDate < d);
  }, [isEdit, watchedDate, existingDates]);

  // Fetch price when date changes and investment has a ticker.
  const fetchPrice = useCallback(
    async (date: string) => {
      if (!ticker || !date) {
        setFetchedPrice(null);
        setFetchedPriceCurrency(null);
        setEffectivePrice(null);
        setPriceConverted(false);
        setPriceFetched(false);
        return;
      }
      setPriceLoading(true);
      setPriceFetched(false);
      const startTime = Date.now();
      try {
        const result = await fetchPriceForDate(ticker, date, category, baseCurrency);
        const elapsed = Date.now() - startTime;
        if (elapsed < PRICE_DISPLAY_DELAY_MS) {
          await new Promise((r) => setTimeout(r, PRICE_DISPLAY_DELAY_MS - elapsed));
        }
        if (result) {
          setFetchedPrice(result.price);
          setFetchedPriceCurrency(result.currency);
          // Use converted price if available, otherwise use original if currencies match.
          if (result.convertedPrice !== null) {
            setEffectivePrice(result.convertedPrice);
            setPriceConverted(true);
          } else if (result.currency === baseCurrency) {
            setEffectivePrice(result.price);
            setPriceConverted(false);
          } else {
            // Currencies don't match and conversion failed.
            setEffectivePrice(null);
            setPriceConverted(false);
          }
        } else {
          setFetchedPrice(null);
          setFetchedPriceCurrency(null);
          setEffectivePrice(null);
          setPriceConverted(false);
        }
      } catch {
        setFetchedPrice(null);
        setFetchedPriceCurrency(null);
        setEffectivePrice(null);
        setPriceConverted(false);
      } finally {
        setPriceLoading(false);
        setPriceFetched(true);
      }
    },
    [ticker, category, baseCurrency],
  );

  // Trigger price fetch on date change.
  useEffect(() => {
    if (open && watchedDate && ticker) {
      fetchPrice(watchedDate);
    }
  }, [open, watchedDate, ticker, fetchPrice]);

  // Derivation: when in quantity mode and effective price is available, derive value from quantity.
  useEffect(() => {
    if (!quantityMode || !effectivePrice || !watchedQuantity) return;
    const qty = parseFloat(watchedQuantity);
    if (!isNaN(qty) && qty > 0) {
      form.setValue('value', (qty * effectivePrice).toFixed(2), { shouldValidate: true });
    }
  }, [watchedQuantity, quantityMode, effectivePrice, form]);

  // Derivation: when NOT in quantity mode and effective price is available, derive quantity from value.
  useEffect(() => {
    if (quantityMode || !effectivePrice || !watchedValue) return;
    const val = parseFloat(watchedValue);
    if (!isNaN(val) && val > 0) {
      form.setValue('quantity', (val / effectivePrice).toFixed(6), { shouldValidate: false });
    }
  }, [watchedValue, quantityMode, effectivePrice, form]);

  // Transaction derivation: same logic, same toggle, same price.
  useEffect(() => {
    if (!quantityMode || !effectivePrice || !watchedTxQuantity || !includeTransaction) return;
    const qty = parseFloat(watchedTxQuantity);
    if (!isNaN(qty) && qty > 0) {
      form.setValue('transactionAmount', (qty * effectivePrice).toFixed(2), {
        shouldValidate: false,
      });
    }
  }, [watchedTxQuantity, quantityMode, effectivePrice, includeTransaction, form]);

  useEffect(() => {
    if (quantityMode || !effectivePrice || !watchedTxAmount || !includeTransaction) return;
    const val = parseFloat(watchedTxAmount);
    if (!isNaN(val) && val > 0) {
      form.setValue('transactionQuantity', (val / effectivePrice).toFixed(6), {
        shouldValidate: false,
      });
    }
  }, [watchedTxAmount, quantityMode, effectivePrice, includeTransaction, form]);

  // Reset form values when the dialog opens.
  useEffect(() => {
    if (open) {
      setFetchedPrice(null);
      setFetchedPriceCurrency(null);
      setEffectivePrice(null);
      setPriceConverted(false);
      setPriceFetched(false);
      setQuantityMode(false);
      form.reset({
        date: cell?.date ?? '',
        value: cell ? String(cell.originalValue) : '',
        quantity: cell?.quantity != null ? String(cell.quantity) : '',
        includeTransaction: !!existingTx,
        transactionAmount: existingTx ? String(existingTx.originalAmount) : '',
        transactionQuantity: existingTx?.quantity != null ? String(existingTx.quantity) : '',
        transactionType: (existingTx?.type as SnapshotFormValues['transactionType']) ?? 'deposit',
      });
    }
  }, [open, cell, existingTx, form]);

  // CEDEAR equivalent underlying shares.
  const underlyingShares = useMemo(() => {
    if (!cedearRatio || !watchedQuantity) return null;
    const qty = parseFloat(watchedQuantity);
    if (isNaN(qty) || qty <= 0) return null;
    return (qty / cedearRatio).toFixed(4);
  }, [cedearRatio, watchedQuantity]);

  async function onSubmit(values: SnapshotFormValues) {
    try {
      await upsertSnapshot(investmentId, {
        date: values.date,
        value: values.value,
        quantity: values.quantity || undefined,
        currency: baseCurrency,
      });

      const wantsTx =
        values.includeTransaction && values.transactionAmount && values.transactionType;

      if (wantsTx && existingTx) {
        await updateTransaction(investmentId, existingTx.id, {
          amount: values.transactionAmount!,
          quantity: values.transactionQuantity || undefined,
          type: values.transactionType!,
        });
      } else if (wantsTx && !existingTx) {
        await createTransaction(investmentId, {
          date: values.date,
          amount: values.transactionAmount!,
          quantity: values.transactionQuantity || undefined,
          currency: baseCurrency,
          type: values.transactionType!,
        });
      } else if (!wantsTx && existingTx) {
        await deleteTransaction(investmentId, existingTx.id);
      }

      toast.success(isEdit ? t('form.updateSuccess') : t('form.createSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('form.saveError'));
    }
  }

  const hasTicker = !!ticker;
  const hasPrice = fetchedPrice !== null;
  const hasEffectivePrice = effectivePrice !== null;
  const showToggle = hasTicker && hasEffectivePrice;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader className="text-left">
          <DialogTitle>{isEdit ? t('form.titleEdit') : t('form.titleCreate')}</DialogTitle>
          <p className="text-paragraph-sm text-muted-foreground">
            {investmentName} ({baseCurrency})
          </p>
        </DialogHeader>

        <Form {...form}>
          <form
            id="snapshot-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <LayoutGroup>
              <motion.div layout transition={{ duration: ANIMATION_DEFAULT }}>
                <FormField
                  control={form.control}
                  name="date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel required>{t('form.date.label')}</FormLabel>
                      <FormControl>
                        <DatePickerInput
                          value={field.value}
                          onChange={field.onChange}
                          disabled={isEdit}
                          placeholder={t('form.date.placeholder')}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </motion.div>

              {/* Price hint + toggle. */}
              <AnimatePresence>
                {hasTicker && watchedDate && (priceLoading || priceFetched) && (
                  <motion.div
                    key="price-hint"
                    layout
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    style={{ overflow: 'hidden', marginTop: -16 }}
                  >
                    <div className="flex items-center justify-between gap-x-3 pt-4">
                      <div className="text-paragraph-xs text-muted-foreground">
                        {priceLoading && (
                          <span className="inline-flex items-center gap-x-1.5">
                            <Loader2 className="size-3 animate-spin" />
                            {t('form.price.loading')}
                          </span>
                        )}
                        {!priceLoading && hasPrice && priceConverted && effectivePrice !== null && (
                          <span>
                            {t('form.price.converted', {
                              originalPrice: fetchedPrice!.toFixed(2),
                              originalCurrency: fetchedPriceCurrency ?? '',
                              price: effectivePrice.toFixed(2),
                              currency: baseCurrency,
                            })}
                          </span>
                        )}
                        {!priceLoading && hasPrice && !priceConverted && hasEffectivePrice && (
                          <span>
                            {t('form.price.found', {
                              price: effectivePrice!.toFixed(2),
                              currency: baseCurrency,
                            })}
                          </span>
                        )}
                        {!priceLoading && hasPrice && !hasEffectivePrice && (
                          <span>
                            {t('form.price.noConversion', {
                              price: fetchedPrice!.toFixed(2),
                              currency: fetchedPriceCurrency ?? '',
                            })}
                          </span>
                        )}
                        {!priceLoading && !hasPrice && <span>{t('form.price.notFound')}</span>}
                      </div>
                      {showToggle && (
                        <div className="flex shrink-0 items-center gap-x-2">
                          <Label
                            htmlFor="quantity-mode"
                            className="text-paragraph-xs cursor-pointer"
                          >
                            {t('form.quantityMode')}
                          </Label>
                          <Switch
                            id="quantity-mode"
                            blue
                            surface
                            checked={quantityMode}
                            onCheckedChange={setQuantityMode}
                          />
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <motion.div
                layout
                transition={{ duration: ANIMATION_DEFAULT }}
                className="flex min-w-0 items-start gap-x-3"
              >
                <FormField
                  control={form.control}
                  name="value"
                  render={({ field }) => (
                    <FormItem className="flex-1 min-w-0" {...(quantityMode ? { inert: true } : {})}>
                      <FormLabel required>{t('form.value.label')}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder={t('form.value.placeholder')}
                          className={cn(
                            'transition-colors',
                            quantityMode && 'bg-muted text-muted-foreground',
                          )}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {hasTicker && (
                  <FormField
                    control={form.control}
                    name="quantity"
                    render={({ field }) => (
                      <FormItem
                        className="flex-1 min-w-0"
                        {...(showToggle && !quantityMode ? { inert: true } : {})}
                      >
                        <FormLabel>{t('form.quantity.label')}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            type="number"
                            step="any"
                            min="0"
                            placeholder={t('form.quantity.placeholder')}
                            className={cn(
                              'transition-colors',
                              showToggle && !quantityMode && 'bg-muted text-muted-foreground',
                            )}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
              </motion.div>

              {/* CEDEAR equivalent. */}
              {cedearRatio && (
                <motion.div layout transition={{ duration: ANIMATION_DEFAULT }}>
                  <InfoHint show={!!underlyingShares} parentGap={16}>
                    {t('form.cedearEquivalent', {
                      quantity: watchedQuantity ?? '',
                      ticker: ticker?.replace('.BA', '') ?? '',
                      shares: underlyingShares ?? '',
                    })}
                  </InfoHint>
                </motion.div>
              )}

              <motion.div
                layout
                transition={{ duration: ANIMATION_DEFAULT }}
                className="flex flex-col gap-y-2"
              >
                <div className="flex items-center gap-x-2">
                  <Checkbox
                    id="include-transaction"
                    checked={includeTransaction}
                    onCheckedChange={(val) => form.setValue('includeTransaction', !!val)}
                  />
                  <Label htmlFor="include-transaction" className="cursor-pointer text-paragraph-sm">
                    {t('form.transaction.include')}
                  </Label>
                </div>
                <WarningHint show={isEarliestSnapshot} parentGap={8}>
                  {t('form.transaction.initialHint')}
                </WarningHint>
              </motion.div>

              <AnimatePresence initial={false}>
                {includeTransaction && (
                  <motion.div
                    layout
                    initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                    exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    style={{ marginTop: -16 }}
                  >
                    <div className="flex min-w-0 flex-wrap items-start gap-x-3 gap-y-4 pt-4">
                      <FormField
                        control={form.control}
                        name="transactionAmount"
                        render={({ field }) => (
                          <FormItem
                            className="flex-1 min-w-0"
                            {...(quantityMode ? { inert: true } : {})}
                          >
                            <FormLabel>{t('form.transaction.amount')}</FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                type="number"
                                step="0.01"
                                min="0"
                                placeholder="0.00"
                                className={cn(
                                  'transition-colors',
                                  quantityMode && 'bg-muted text-muted-foreground',
                                )}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {hasTicker && (
                        <FormField
                          control={form.control}
                          name="transactionQuantity"
                          render={({ field }) => (
                            <FormItem
                              className="flex-1 min-w-0"
                              {...(showToggle && !quantityMode ? { inert: true } : {})}
                            >
                              <FormLabel>{t('form.transaction.quantity')}</FormLabel>
                              <FormControl>
                                <Input
                                  {...field}
                                  type="number"
                                  step="any"
                                  min="0"
                                  placeholder="0"
                                  className={cn(
                                    'transition-colors',
                                    showToggle && !quantityMode && 'bg-muted text-muted-foreground',
                                  )}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}

                      <FormField
                        control={form.control}
                        name="transactionType"
                        render={({ field }) => (
                          <FormItem className="flex-1">
                            <FormLabel>{t('form.transaction.type')}</FormLabel>
                            <Select value={field.value ?? 'deposit'} onValueChange={field.onChange}>
                              <FormControl>
                                <SelectTrigger className="w-full">
                                  <SelectValue />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {TRANSACTION_TYPES.map((type) => (
                                  <SelectItem key={type} value={type}>
                                    {t(`form.transaction.types.${type}`)}
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
            </LayoutGroup>
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="snapshot-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
