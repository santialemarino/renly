'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, LayoutGroup, motion } from 'motion/react';
import { useLocale, useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import {
  createInvestment,
  updateInvestment,
} from '@/app/(protected)/investments/investments-actions';
import {
  buildInvestmentFormSchema,
  type InvestmentFormValues,
} from '@/app/(protected)/investments/investments-form-schema';
import { ComboboxMultiSelect } from '@/components/combobox-multi-select';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { Investment, InvestmentGroup } from '@/lib/api/investments';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { CATEGORY_CAPABILITIES, type InvestmentCategory } from '@/lib/constants/categories';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';
import { sortCategoriesByLabel } from '@/lib/utils/categories';

interface InvestmentFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investment?: Investment;
  groups: InvestmentGroup[];
  preferredCurrencies?: string[];
  onSuccess: () => void;
}

export function InvestmentFormDialog({
  open,
  onOpenChange,
  investment,
  groups,
  preferredCurrencies,
  onSuccess,
}: InvestmentFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildInvestmentFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<InvestmentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      category: undefined as unknown as InvestmentFormValues['category'],
      baseCurrency: '',
      ticker: '',
      broker: '',
      notes: '',
      groupIds: [],
    },
  });

  const watchedCategory = useWatch({ control: form.control, name: 'category' }) as
    | InvestmentCategory
    | undefined;

  const isEdit = !!investment;
  const currencyLocked = isEdit && (investment?.hasSnapshots ?? false);
  const capabilities = watchedCategory ? CATEGORY_CAPABILITIES[watchedCategory] : null;
  const showTicker = capabilities?.hasTicker ?? false;
  const tickerHint =
    watchedCategory && showTicker ? t(`form.ticker.hints.${watchedCategory}`) : null;

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: investment,
    toValues: (inv) => ({
      name: inv?.name ?? '',
      category: (inv?.category ?? undefined) as unknown as InvestmentFormValues['category'],
      baseCurrency: inv?.baseCurrency ?? '',
      ticker: inv?.ticker ?? '',
      broker: inv?.broker ?? '',
      notes: inv?.notes ?? '',
      groupIds: inv?.groups.map((g) => g.id) ?? [],
    }),
    onSuccess,
  });

  // Clear ticker when switching to a category that doesn't support it.
  useEffect(() => {
    if (!showTicker && form.getValues('ticker')) {
      form.setValue('ticker', '');
    }
  }, [showTicker, form]);

  async function onSubmit(values: InvestmentFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updateInvestment(investment.id, values) : createInvestment(values)),
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
            id="investment-form"
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
                name="category"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.category.label')}</FormLabel>
                    <Select value={field.value ?? ''} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.category.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {sortCategoriesByLabel(tCommon, locale).map((cat) => (
                          <SelectItem key={cat} value={cat}>
                            {tCommon(`categories.${cat}`)}
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
                name="baseCurrency"
                render={({ field }) => (
                  <FormItem required className="flex-1 min-w-0">
                    <FormLabel>{t('form.currency.label')}</FormLabel>
                    <FormControl>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div>
                            <CurrencyCombobox
                              compact
                              value={field.value || null}
                              exclude={[]}
                              preferredCurrencies={preferredCurrencies}
                              disabled={currencyLocked}
                              placeholder={t('form.currency.placeholder')}
                              searchPlaceholder={t('form.currency.searchPlaceholder')}
                              noResults={t('form.currency.noResults')}
                              onChange={field.onChange}
                            />
                          </div>
                        </TooltipTrigger>
                        {currencyLocked && (
                          <TooltipContent>{t('form.currency.locked')}</TooltipContent>
                        )}
                      </Tooltip>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <LayoutGroup>
              <div className="flex min-w-0 items-start gap-x-3">
                <AnimatePresence initial={false} mode="popLayout">
                  {showTicker && (
                    <motion.div
                      key="ticker"
                      layout
                      initial={{ opacity: 0, width: 0, marginRight: -12 }}
                      animate={{ opacity: 1, width: 'auto', marginRight: 0 }}
                      exit={{ opacity: 0, width: 0, marginRight: -12 }}
                      transition={{ duration: ANIMATION_DEFAULT }}
                      style={{ overflow: 'hidden' }}
                      className="flex-1 min-w-0"
                    >
                      <FormField
                        control={form.control}
                        name="ticker"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {watchedCategory && t.has(`form.ticker.label.${watchedCategory}`)
                                ? t(`form.ticker.label.${watchedCategory}`)
                                : t('form.ticker.label.default')}
                            </FormLabel>
                            <FormControl>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Input
                                    {...field}
                                    placeholder={t('form.ticker.placeholder')}
                                    onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                                  />
                                </TooltipTrigger>
                                {tickerHint && <TooltipContent>{tickerHint}</TooltipContent>}
                              </Tooltip>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <motion.div
                  layout
                  transition={{ duration: ANIMATION_DEFAULT }}
                  className="flex-1 min-w-0"
                >
                  <FormField
                    control={form.control}
                    name="broker"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('form.broker.label')}</FormLabel>
                        <FormControl>
                          <Input {...field} placeholder={t('form.broker.placeholder')} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </motion.div>
              </div>
            </LayoutGroup>

            {groups.length > 0 && (
              <FormField
                control={form.control}
                name="groupIds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('form.groups.label')}</FormLabel>
                    <ComboboxMultiSelect
                      items={groups.map((g) => ({ id: g.id, label: g.name }))}
                      selectedIds={field.value ?? []}
                      onToggle={(id) => {
                        const current = field.value ?? [];
                        field.onChange(
                          current.includes(id) ? current.filter((i) => i !== id) : [...current, id],
                        );
                      }}
                      placeholder={t('form.groups.placeholder')}
                      searchPlaceholder={t('form.groups.placeholder')}
                      emptyMessage={t('form.groups.empty')}
                      showChips
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
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
          <Button blue type="submit" form="investment-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
