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
} from '@repo/ui/components';
import { createOrReplaceReconciliation } from '@/app/(protected)/credit-cards/credit-card-actions';
import {
  buildReconciliationFormSchema,
  type ReconciliationFormValues,
} from '@/app/(protected)/credit-cards/reconciliation-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import { StyledHint } from '@/components/styled-hint';
import type { StatementPeriod } from '@/lib/api/card-reconciliations';
import { useFormatters } from '@/lib/i18n/formatters';

interface ReconciliationFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  statement: StatementPeriod | null;
  onSuccess: () => void;
}

export function ReconciliationFormDialog({
  open,
  onOpenChange,
  cardId,
  statement,
  onSuccess,
}: ReconciliationFormDialogProps) {
  const fmt = useFormatters();
  const t = useTranslations('creditCards.reconciliations');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildReconciliationFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const isReplace = !!statement?.reconciliation;
  const isStale = !!statement?.reconciliation?.isStale;

  const form = useForm<ReconciliationFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      currency: '',
      periodStart: '',
      periodEnd: '',
      statementBalance: '',
    },
  });

  // Re-seed defaults whenever the dialog opens with a different statement.
  useEffect(() => {
    if (open && statement) {
      form.reset({
        currency: statement.currency,
        periodStart: statement.periodStart,
        periodEnd: statement.periodEnd,
        statementBalance: statement.reconciliation?.statementBalance ?? '',
      });
    }
  }, [open, statement, form]);

  const statementBalanceRaw = useWatch({ control: form.control, name: 'statementBalance' });

  // Live preview: difference + which side (expense / income / none).
  const computed = statement ? Number(statement.computedBalance) : 0;
  const entered = Number(statementBalanceRaw || '0');
  const diff = Number.isFinite(entered) ? entered - computed : 0;
  // Both directions post one SIGNED, card-linked adjustment expense — a bucket balance only moves on
  // expenses and settlements, so a credit is a negative expense, never an income. Named for what the
  // user sees (the bank charged more / credited some back), not for the row type.
  const diffSide: 'charge' | 'credit' | 'zero' = diff > 0 ? 'charge' : diff < 0 ? 'credit' : 'zero';

  async function onSubmit(values: ReconciliationFormValues) {
    if (!statement) return;
    try {
      await createOrReplaceReconciliation(cardId, values);
      toast.success(isReplace ? t('form.replaceSuccess') : t('form.createSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('form.saveError'));
    }
  }

  if (!statement) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* Hint banners live inside the DialogHeader so the header's pb-4 fires once at the
            bottom of the whole banner block, matching the gap-4 between subsequent siblings. */}
        <DialogHeader>
          <DialogTitle>{t('form.title')}</DialogTitle>
          <p className="text-paragraph-sm text-muted-foreground">
            {t('form.periodRange', {
              start: fmt.date(statement.periodStart),
              end: fmt.date(statement.periodEnd),
            })}
          </p>
          {isStale && <StyledHint variant="warning">{t('form.staleBanner')}</StyledHint>}
          {isReplace && !isStale && statement.reconciliation && (
            <StyledHint variant="info">
              {t('form.replaceBanner', {
                date: fmt.timestampDate(statement.reconciliation.reconciledAt),
              })}
            </StyledHint>
          )}
        </DialogHeader>

        <Form {...form}>
          <form
            id="reconciliation-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex flex-col gap-y-1">
              <span className="text-paragraph-sm-medium">{t('form.computedBalance')}</span>
              <span className="text-paragraph tabular-nums">
                {fmt.amount(statement.computedBalance, statement.currency)}{' '}
                <span className="text-paragraph-xs text-muted-foreground">
                  {statement.currency}
                </span>
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
                  <FormLabel>{t('form.bankBalance')}</FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      currency={statement.currency}
                      placeholder={t('form.bankBalancePlaceholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {statementBalanceRaw !== '' && Number.isFinite(entered) && (
              <div className="flex flex-col gap-y-1 p-3 bg-muted/40 rounded-md">
                <span className="text-paragraph-xs-medium text-muted-foreground">
                  {t('form.difference')}
                </span>
                <span className="text-paragraph tabular-nums">
                  {diff === 0 ? '0' : fmt.amount(String(diff), statement.currency)}{' '}
                  <span className="text-paragraph-xs text-muted-foreground">
                    {statement.currency}
                  </span>
                </span>
                <span className="text-paragraph-xs text-muted-foreground">
                  {diffSide === 'charge' &&
                    t('form.differenceChargePreview', {
                      amount: fmt.amount(String(Math.abs(diff)), statement.currency),
                      currency: statement.currency,
                    })}
                  {diffSide === 'credit' &&
                    t('form.differenceCreditPreview', {
                      amount: fmt.amount(String(Math.abs(diff)), statement.currency),
                      currency: statement.currency,
                    })}
                  {diffSide === 'zero' && t('form.differenceZeroPreview')}
                </span>
              </div>
            )}
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button
            blue
            type="submit"
            form="reconciliation-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting
              ? t('form.saveLoading')
              : isReplace
                ? t('form.replaceLabel')
                : t('form.saveLabel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
