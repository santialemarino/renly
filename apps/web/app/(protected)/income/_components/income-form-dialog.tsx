'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useLocale, useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
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
import { createIncome, updateIncome } from '@/app/(protected)/income/income-actions';
import {
  buildIncomeFormSchema,
  type IncomeFormValues,
} from '@/app/(protected)/income/income-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { IncomeEntry } from '@/lib/api/income';
import { sortIncomeCategoriesByLabel } from '@/lib/utils/categories';
import { blockNegativeNumberKeys } from '@/lib/utils/form-events';

interface IncomeFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  income?: IncomeEntry;
  preferredCurrencies?: string[];
  onSuccess: () => void;
}

export function IncomeFormDialog({
  open,
  onOpenChange,
  income,
  preferredCurrencies,
  onSuccess,
}: IncomeFormDialogProps) {
  const locale = useLocale();
  const t = useTranslations('income');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildIncomeFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<IncomeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      currency: '',
      category: undefined,
      notes: '',
    },
  });

  const isEdit = !!income;

  const sortedCategories = sortIncomeCategoriesByLabel((key) => t(key), locale);

  // Reset form when dialog opens or income entry changes.
  useEffect(() => {
    if (open) {
      form.reset({
        date: income?.date ?? '',
        amount: income?.amount ? String(Number(income.amount)) : '',
        currency: income?.currency ?? '',
        category: (income?.category ?? undefined) as IncomeFormValues['category'],
        notes: income?.notes ?? '',
      });
    }
  }, [open, income, form]);

  async function onSubmit(values: IncomeFormValues) {
    try {
      if (isEdit) {
        await updateIncome(income.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createIncome(values);
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
            id="income-form"
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

            <FormField
              control={form.control}
              name="category"
              render={({ field }) => (
                <FormItem>
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
          <Button blue type="submit" form="income-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
