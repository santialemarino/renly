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
  Textarea,
} from '@repo/ui/components';
import { createSettlement } from '@/app/(protected)/credit-cards/credit-card-actions';
import {
  buildSettlementFormSchema,
  type SettlementFormValues,
} from '@/app/(protected)/credit-cards/settlement-form-schema';
import { DatePickerInput } from '@/components/date-picker-input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { blockNegativeNumberKeys } from '@/lib/utils/form-events';

interface SettlementFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cardId: number;
  cardCurrency: string;
  onSuccess: () => void;
}

export function SettlementFormDialog({
  open,
  onOpenChange,
  cardId,
  cardCurrency,
  onSuccess,
}: SettlementFormDialogProps) {
  const t = useTranslations('creditCards');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildSettlementFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<SettlementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      amount: '',
      notes: '',
    },
  });

  // Reset form when dialog opens.
  useEffect(() => {
    if (open) {
      form.reset({ date: '', amount: '', notes: '' });
    }
  }, [open, form]);

  async function onSubmit(values: SettlementFormValues) {
    try {
      await createSettlement(cardId, { ...values, currency: cardCurrency });
      toast.success(t('settlements.createSuccess'));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t('settlements.createError'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settlements.addTitle')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="settlement-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <div className="flex min-w-0 items-start gap-x-3">
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('settlements.form.date')}</FormLabel>
                    <FormControl>
                      <DatePickerInput
                        value={field.value || undefined}
                        onChange={field.onChange}
                        placeholder={t('settlements.form.datePlaceholder')}
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
                    <FormLabel required>{t('settlements.form.amount')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        step="0.01"
                        min="0"
                        onKeyDown={blockNegativeNumberKeys}
                        placeholder="0.00"
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
                  <FormLabel>{t('settlements.form.notes')}</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder={t('settlements.form.notesPlaceholder')}
                      rows={2}
                    />
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
          <Button blue type="submit" form="settlement-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
