'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
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
  Textarea,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import {
  createInvestment,
  updateInvestment,
} from '@/app/(protected)/investments/investments-actions';
import {
  buildInvestmentFormSchema,
  INVESTMENT_CATEGORIES,
  type InvestmentFormValues,
} from '@/app/(protected)/investments/investments-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { Investment, InvestmentGroup } from '@/lib/api/investments';

interface InvestmentFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investment?: Investment;
  groups: InvestmentGroup[];
  onSuccess: () => void;
}

export function InvestmentFormDialog({
  open,
  onOpenChange,
  investment,
  groups,
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
        broker: investment?.broker ?? '',
        notes: investment?.notes ?? '',
        groupIds: investment?.groups.map((g) => g.id) ?? [],
      });
    }
  }, [open, investment, form]);

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
                        {INVESTMENT_CATEGORIES.map((cat) => (
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

            {groups.length > 0 && (
              <FormField
                control={form.control}
                name="groupIds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('form.groups.label')}</FormLabel>
                    <div className="flex flex-col gap-y-2">
                      {groups.map((group) => {
                        const checked = (field.value ?? []).includes(group.id);
                        return (
                          <div key={group.id} className="flex items-center gap-x-2">
                            <Checkbox
                              id={`group-${group.id}`}
                              checked={checked}
                              onCheckedChange={(val) => {
                                const current = field.value ?? [];
                                field.onChange(
                                  val
                                    ? [...current, group.id]
                                    : current.filter((id) => id !== group.id),
                                );
                              }}
                            />
                            <Label
                              htmlFor={`group-${group.id}`}
                              className="cursor-pointer text-paragraph-sm"
                            >
                              {group.name}
                            </Label>
                          </div>
                        );
                      })}
                    </div>
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
