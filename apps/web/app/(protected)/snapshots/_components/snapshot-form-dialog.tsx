'use client';

import { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
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
} from '@repo/ui/components';
import {
  buildSnapshotFormSchema,
  TRANSACTION_TYPES,
  type SnapshotFormValues,
} from '@/app/(protected)/snapshots/snapshot-form-schema';
import {
  createTransaction,
  deleteTransaction,
  updateTransaction,
  upsertSnapshot,
} from '@/app/(protected)/snapshots/snapshots-actions';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { WarningHint } from '@/components/warning-hint';
import type { SnapshotGridCell } from '@/lib/api/snapshots';

interface SnapshotFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investmentId: number;
  investmentName: string;
  baseCurrency: string;
  existingDates: string[];
  cell?: SnapshotGridCell;
  onSuccess: () => void;
}

export function SnapshotFormDialog({
  open,
  onOpenChange,
  investmentId,
  investmentName,
  baseCurrency,
  existingDates,
  cell,
  onSuccess,
}: SnapshotFormDialogProps) {
  const t = useTranslations('snapshots');
  const tCommon = useTranslations('common');
  const isEdit = !!cell;
  const existingTx = cell?.transaction ?? null;

  const existingYearMonths = useMemo(
    () => new Set(existingDates.map((d) => d.slice(0, 7))),
    [existingDates],
  );

  const schema = useMemo(
    () =>
      buildSnapshotFormSchema(
        tCommon('form.errors.required'),
        t('form.date.duplicate'),
        existingYearMonths,
        isEdit,
      ),
    [tCommon, t, existingYearMonths, isEdit],
  );

  const form = useForm<SnapshotFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: '',
      value: '',
      includeTransaction: false,
      transactionAmount: '',
      transactionType: 'deposit',
    },
  });

  const includeTransaction = form.watch('includeTransaction');
  const watchedDate = form.watch('date');

  const MIN_REASONABLE_YEAR = 1900;

  // True when the snapshot being created would be the earliest for this investment.
  // Only evaluates once the date has a reasonable year to avoid flickering during input.
  const isEarliestSnapshot = useMemo(() => {
    if (isEdit || !watchedDate) return false;
    const year = new Date(watchedDate).getFullYear();
    if (isNaN(year) || year < MIN_REASONABLE_YEAR) return false;
    if (existingDates.length === 0) return true;
    return existingDates.every((d) => watchedDate < d);
  }, [isEdit, watchedDate, existingDates]);

  // Reset form values when the dialog opens.
  useEffect(() => {
    if (open) {
      // Always use original (base currency) values for editing to avoid currency mismatch on save.
      form.reset({
        date: cell?.date ?? '',
        value: cell ? String(cell.originalValue) : '',
        includeTransaction: !!existingTx,
        transactionAmount: existingTx ? String(existingTx.originalAmount) : '',
        transactionType: (existingTx?.type as SnapshotFormValues['transactionType']) ?? 'deposit',
      });
    }
  }, [open, cell, existingTx, form]);

  async function onSubmit(values: SnapshotFormValues) {
    try {
      await upsertSnapshot(investmentId, {
        date: values.date,
        value: values.value,
        currency: baseCurrency,
      });

      const wantsTx =
        values.includeTransaction && values.transactionAmount && values.transactionType;

      if (wantsTx && existingTx) {
        // Update existing transaction.
        await updateTransaction(investmentId, existingTx.id, {
          amount: values.transactionAmount!,
          type: values.transactionType!,
        });
      } else if (wantsTx && !existingTx) {
        // Create new transaction.
        await createTransaction(investmentId, {
          date: values.date,
          amount: values.transactionAmount!,
          currency: baseCurrency,
          type: values.transactionType!,
        });
      } else if (!wantsTx && existingTx) {
        // Remove existing transaction.
        await deleteTransaction(investmentId, existingTx.id);
      }

      toast.success(isEdit ? t('form.updateSuccess') : t('form.createSuccess'));
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
          <p className="text-paragraph-sm text-muted-foreground">
            {investmentName} ({baseCurrency})
          </p>
        </DialogHeader>

        <Form {...form}>
          <form
            id="snapshot-form"
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
                    <FormLabel required>{t('form.date.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} type="date" disabled={isEdit} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="value"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel required>{t('form.value.label')}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder={t('form.value.placeholder')}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="flex flex-col gap-y-2">
              <div className="flex items-center gap-x-2">
                <Checkbox
                  id="include-transaction"
                  checked={includeTransaction}
                  onCheckedChange={(val) => form.setValue('includeTransaction', !!val)}
                />
                <Label htmlFor="include-transaction" className="cursor-pointer text-paragraph-sm">
                  {t('form.transaction.include')}
                </Label>
              </div>
              <WarningHint show={isEarliestSnapshot} parentGap={8}>
                {t('form.transaction.initialHint')}
              </WarningHint>
            </div>

            <AnimatePresence initial={false}>
              {includeTransaction && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.25 }}
                  style={{ overflow: 'hidden', marginTop: -16 }}
                >
                  <div className="flex min-w-0 items-start gap-x-3 pt-4">
                    <FormField
                      control={form.control}
                      name="transactionAmount"
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormLabel>{t('form.transaction.amount')}</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              type="number"
                              step="0.01"
                              min="0"
                              placeholder="0.00"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="transactionType"
                      render={({ field }) => (
                        <FormItem className="flex-1">
                          <FormLabel>{t('form.transaction.type')}</FormLabel>
                          <Select value={field.value ?? 'deposit'} onValueChange={field.onChange}>
                            <FormControl>
                              <SelectTrigger className="w-full">
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {TRANSACTION_TYPES.map((type) => (
                                <SelectItem key={type} value={type}>
                                  {t(`form.transaction.types.${type}`)}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="snapshot-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
