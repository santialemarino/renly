'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';
import {
  fetchAccountComputedBalance,
  reconcileAccount,
} from '@/app/(protected)/accounts/account-actions';
import {
  buildAccountReconcileFormSchema,
  type AccountReconcileFormValues,
} from '@/app/(protected)/accounts/account-reconcile-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { Account } from '@/lib/api/accounts';
import { useFormatters } from '@/lib/i18n/formatters';

interface AccountReconcileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  account: Account | null;
  onSuccess: () => void;
}

// Today in the user's own calendar, as the YYYY-MM-DD the date input and the API both expect.
// Built from local parts (not toISOString, which shifts a negative-UTC-offset user to yesterday).
function todayIsoDate(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function AccountReconcileDialog({
  open,
  onOpenChange,
  account,
  onSuccess,
}: AccountReconcileDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('accounts.reconciliations');
  const tForm = useTranslations('accounts.form');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildAccountReconcileFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<AccountReconcileFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { asOfDate: '', statementBalance: '' },
  });

  const [computedBalance, setComputedBalance] = useState<string | null>(null);
  const [loadingBalance, setLoadingBalance] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const asOfDate = useWatch({ control: form.control, name: 'asOfDate' });
  const statementBalanceRaw = useWatch({ control: form.control, name: 'statementBalance' });

  // Re-seed on open: the date defaults to today, which is the overwhelmingly common case.
  useEffect(() => {
    if (open) {
      form.reset({ asOfDate: todayIsoDate(), statementBalance: '' });
      setSubmitError(null);
    }
  }, [open, form]);

  // The balance being trued up depends on the chosen date, so re-read it whenever that date moves.
  useEffect(() => {
    if (!open || !account || !asOfDate) return;
    let cancelled = false;
    setLoadingBalance(true);
    fetchAccountComputedBalance(account.id, asOfDate)
      .then((balance) => {
        if (!cancelled) setComputedBalance(balance);
      })
      .catch(() => {
        if (!cancelled) setComputedBalance(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingBalance(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, account, asOfDate]);

  // Live preview: the gap and which side it lands on. Positive means the account really holds more
  // than Renly knew, so the adjustment is an income (the mirror of the card side's convention).
  const computed = computedBalance !== null ? Number(computedBalance) : 0;
  const entered = Number(statementBalanceRaw || '0');
  const diff = Number.isFinite(entered) ? entered - computed : 0;
  const diffSide: 'income' | 'expense' | 'zero' =
    diff > 0 ? 'income' : diff < 0 ? 'expense' : 'zero';
  const showPreview =
    computedBalance !== null &&
    !loadingBalance &&
    statementBalanceRaw !== '' &&
    Number.isFinite(entered);

  async function onSubmit(values: AccountReconcileFormValues) {
    if (!account) return;
    setSubmitError(null);
    const result = await reconcileAccount(account.id, values);
    if (!result.ok) {
      setSubmitError(result.error || t('form.saveError'));
      return;
    }
    toast.success(t('form.success'));
    onSuccess();
    onOpenChange(false);
  }

  if (!account) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('form.title', { name: account.name })}</DialogTitle>
          {/* The semantic description (not a bare <p>) so Radix wires aria-describedby. */}
          <DialogDescription className="text-paragraph-sm">
            {t('form.description')}
          </DialogDescription>
          {submitError && <StyledHint variant="warning">{submitError}</StyledHint>}
        </DialogHeader>

        <Form {...form}>
          <form
            id="account-reconcile-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="asOfDate"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.asOfDate.label')}</FormLabel>
                  <FormControl>
                    <DatePickerInput
                      value={field.value || undefined}
                      onChange={field.onChange}
                      placeholder={t('form.asOfDate.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex flex-col gap-y-1">
              <span className="text-paragraph-sm-medium">{t('form.computedBalance')}</span>
              <span className="text-paragraph tabular-nums">
                {loadingBalance || computedBalance === null ? (
                  <span className="text-muted-foreground">{t('form.computedBalanceLoading')}</span>
                ) : (
                  <>
                    {fmt.amount(computedBalance, account.currency)}{' '}
                    <span className="text-paragraph-xs text-muted-foreground">
                      {account.currency}
                    </span>
                  </>
                )}
              </span>
              <span className="text-paragraph-xs text-muted-foreground">
                {t('form.computedBalanceHint')}
              </span>
            </div>

            <FormField
              control={form.control}
              name="statementBalance"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.realBalance.label')}</FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      currency={account.currency}
                      placeholder={t('form.realBalance.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {showPreview && (
              <div className="flex flex-col gap-y-1 p-3 bg-muted/40 rounded-md">
                <span className="text-paragraph-xs-medium text-muted-foreground">
                  {t('form.difference')}
                </span>
                <span className="text-paragraph tabular-nums">
                  {diff === 0 ? '0' : fmt.amount(String(diff), account.currency)}{' '}
                  <span className="text-paragraph-xs text-muted-foreground">
                    {account.currency}
                  </span>
                </span>
                <span className="text-paragraph-xs text-muted-foreground">
                  {diffSide === 'income' &&
                    t('form.differenceIncomePreview', {
                      amount: fmt.amount(String(Math.abs(diff)), account.currency),
                      currency: account.currency,
                    })}
                  {diffSide === 'expense' &&
                    t('form.differenceExpensePreview', {
                      amount: fmt.amount(String(Math.abs(diff)), account.currency),
                      currency: account.currency,
                    })}
                  {diffSide === 'zero' && t('form.differenceZeroPreview')}
                </span>
              </div>
            )}
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tForm('cancel')}
          </Button>
          <Button
            blue
            type="submit"
            form="account-reconcile-form"
            disabled={form.formState.isSubmitting || loadingBalance}
          >
            {form.formState.isSubmitting ? t('form.saveLoading') : t('form.saveLabel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
