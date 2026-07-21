'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
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
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { createAccount, updateAccount } from '@/app/(protected)/accounts/account-actions';
import {
  buildAccountFormSchema,
  type AccountFormValues,
} from '@/app/(protected)/accounts/account-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { Account } from '@/lib/api/accounts';
import { ACCOUNT_TYPES } from '@/lib/constants/accounts';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface AccountFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account?: Account;
  preferredCurrencies?: string[];
  onSuccess: () => void;
}

export function AccountFormDialog({
  open,
  onOpenChange,
  account,
  preferredCurrencies,
  onSuccess,
}: AccountFormDialogProps) {
  const t = useTranslations('accounts');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildAccountFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<AccountFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      type: undefined,
      currency: '',
      openingBalance: '',
      openingDate: '',
      notes: '',
    },
  });

  const isEdit = !!account;
  // Currency is locked once money links to the account — changing it would mix currencies in the
  // derived balance (mirrors the investment base-currency lock). The API is the backstop (409).
  const currencyLocked = isEdit && (account?.hasLinks ?? false);
  const watchedCurrency = useWatch({ control: form.control, name: 'currency' });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: account,
    toValues: (a) => ({
      name: a?.name ?? '',
      type: (a?.type ?? undefined) as AccountFormValues['type'],
      currency: a?.currency ?? '',
      openingBalance: a?.openingBalance ? String(Number(a.openingBalance)) : '',
      openingDate: a?.openingDate ?? '',
      notes: a?.notes ?? '',
    }),
    onSuccess,
  });

  async function onSubmit(values: AccountFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updateAccount(account.id, values) : createAccount(values)),
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
            id="account-form"
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
                name="type"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.type.label')}</FormLabel>
                    <FormControl>
                      <FormCombobox
                        value={field.value ?? ''}
                        onValueChange={(v) => field.onChange(v as AccountFormValues['type'])}
                        placeholder={t('form.type.placeholder')}
                        options={ACCOUNT_TYPES.map((type) => ({
                          value: type,
                          label: t(`types.${type}`),
                        }))}
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

            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="openingBalance"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>{t('form.openingBalance.label')}</FormLabel>
                    <FormControl>
                      <LocaleAmountInput
                        {...field}
                        currency={watchedCurrency || undefined}
                        placeholder={t('form.openingBalance.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="openingDate"
                render={({ field }) => (
                  <FormItem required className="flex-1">
                    <FormLabel>{t('form.openingDate.label')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('form.openingDate.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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
          <Button blue type="submit" form="account-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
