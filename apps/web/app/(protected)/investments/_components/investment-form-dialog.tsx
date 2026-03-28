'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
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
import { CATEGORY_CAPABILITIES, type InvestmentCategory } from '@/lib/constants/categories';
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
  const t = useTranslations('investments');
  const tCommon = useTranslations('common');
  const isEdit = !!investment;

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

  // Reset form values when the dialog opens or the target investment changes.
  useEffect(() => {
    if (open) {
      form.reset({
        name: investment?.name ?? '',
        category: (investment?.category ??
          undefined) as unknown as InvestmentFormValues['category'],
        baseCurrency: investment?.baseCurrency ?? '',
        ticker: investment?.ticker ?? '',
        broker: investment?.broker ?? '',
        notes: investment?.notes ?? '',
        groupIds: investment?.groups.map((g) => g.id) ?? [],
      });
    }
  }, [open, investment, form]);

  const watchedCategory = useWatch({ control: form.control, name: 'category' }) as
    | InvestmentCategory
    | undefined;
  const capabilities = watchedCategory ? CATEGORY_CAPABILITIES[watchedCategory] : null;
  const showTicker = capabilities?.hasTicker ?? false;

  // Clear ticker when switching to a category that doesn't support it.
  useEffect(() => {
    if (!showTicker && form.getValues('ticker')) {
      form.setValue('ticker', '');
    }
  }, [showTicker, form]);

  // Build the ticker placeholder from category-specific hints.
  const tickerPlaceholder =
    watchedCategory && showTicker
      ? t(`form.ticker.hints.${watchedCategory}`)
      : t('form.ticker.placeholder');

  async function onSubmit(values: InvestmentFormValues) {
    try {
      if (isEdit) {
        await updateInvestment(investment.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createInvestment(values);
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
            id="investment-form"
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
                name="category"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.category.label')}</FormLabel>
                    <Select value={field.value ?? ''} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('form.category.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {sortCategoriesByLabel(tCommon).map((cat) => (
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
              {showTicker && (
                <FormField
                  control={form.control}
                  name="ticker"
                  render={({ field }) => (
                    <FormItem className="flex-1 min-w-0">
                      <FormLabel>{t('form.ticker.label')}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={tickerPlaceholder}
                          onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={form.control}
                name="broker"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-0">
                    <FormLabel>{t('form.broker.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('form.broker.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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
