'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
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
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import {
  createCreditCard,
  updateCreditCard,
} from '@/app/(protected)/credit-cards/credit-card-actions';
import {
  buildCreditCardFormSchema,
  type CreditCardFormValues,
} from '@/app/(protected)/credit-cards/credit-card-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { CreditCard } from '@/lib/api/credit-cards';

interface CreditCardFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  card?: CreditCard;
  preferredCurrencies?: string[];
  onSuccess: () => void;
}

export function CreditCardFormDialog({
  open,
  onOpenChange,
  card,
  preferredCurrencies,
  onSuccess,
}: CreditCardFormDialogProps) {
  const t = useTranslations('creditCards');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildCreditCardFormSchema(tCommon('form.errors.required'), t('form.invalidDay')),
    [t, tCommon],
  );

  const form = useForm<CreditCardFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      closingDay: '',
      dueDay: '',
      currency: '',
    },
  });

  const isEdit = !!card;

  // Reset form when dialog opens or card changes.
  useEffect(() => {
    if (open) {
      form.reset({
        name: card?.name ?? '',
        closingDay: card ? String(card.closingDay) : '',
        dueDay: card ? String(card.dueDay) : '',
        currency: card?.currency ?? '',
      });
    }
  }, [open, card, form]);

  async function onSubmit(values: CreditCardFormValues) {
    try {
      if (isEdit) {
        await updateCreditCard(card.id, values);
        toast.success(t('form.updateSuccess'));
      } else {
        await createCreditCard(values);
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
            id="credit-card-form"
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
                name="closingDay"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.closingDay.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        inputMode="numeric"
                        placeholder={t('form.closingDay.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="dueDay"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.dueDay.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        inputMode="numeric"
                        placeholder={t('form.dueDay.placeholder')}
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
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="credit-card-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
