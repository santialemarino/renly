'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

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
import { IntegerInput } from '@/components/integer-input';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { CreditCard } from '@/lib/api/credit-cards';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface CreditCardFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  card?: CreditCard;
  preferredCurrencies?: string[];
  onSuccess: () => void;
  // Fires only on CREATE success with the freshly-created card, before onSuccess.
  // PaymentMethodFields uses it to append + auto-select the card inline.
  onCreated?: (card: CreditCard) => void;
}

export function CreditCardFormDialog({
  open,
  onOpenChange,
  card,
  preferredCurrencies,
  onSuccess,
  onCreated,
}: CreditCardFormDialogProps) {
  const t = useTranslations('creditCards');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () =>
      buildCreditCardFormSchema(
        tCommon('form.errors.required'),
        t('form.invalidDay'),
        t('form.monthlyPayment.invalid'),
      ),
    [t, tCommon],
  );

  const form = useForm<CreditCardFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      closingDay: '',
      dueDay: '',
      currency: '',
      monthlyPayment: '',
    },
  });

  const isEdit = !!card;

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: card,
    toValues: (c) => ({
      name: c?.name ?? '',
      closingDay: c ? String(c.closingDay) : '',
      dueDay: c ? String(c.dueDay) : '',
      currency: c?.currency ?? '',
      monthlyPayment: c?.monthlyPayment != null ? String(c.monthlyPayment) : '',
    }),
    onSuccess,
  });

  async function onSubmit(values: CreditCardFormValues) {
    await submitWithLifecycle(
      async () => {
        if (isEdit) {
          await updateCreditCard(card.id, values);
        } else {
          const created = await createCreditCard(values);
          onCreated?.(created);
        }
      },
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
            id="credit-card-form"
            className="flex flex-col min-w-0 gap-y-4"
            // Stop propagation so the submit doesn't bubble up the React tree to a host form
            // when this dialog is stacked inside one (PaymentMethodFields' inline card creation).
            onSubmit={(e) => {
              e.stopPropagation();
              void form.handleSubmit(onSubmit)(e);
            }}
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
                name="closingDay"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.closingDay.label')}</FormLabel>
                    <FormControl>
                      <IntegerInput {...field} placeholder={t('form.closingDay.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="dueDay"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.dueDay.label')}</FormLabel>
                    <FormControl>
                      <IntegerInput {...field} placeholder={t('form.dueDay.placeholder')} />
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
              name="monthlyPayment"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.monthlyPayment.label')}</FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      currency={form.watch('currency') || undefined}
                      placeholder={t('form.monthlyPayment.placeholder')}
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('form.monthlyPayment.hint')}
                  </p>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('form.monthlyPayment.overlapHint')}
                  </p>
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
          <Button blue type="submit" form="credit-card-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
