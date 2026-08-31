'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Switch,
} from '@repo/ui/components';
import { updateGroupMoneySettings } from '@/app/(protected)/shared/settlement-actions';
import {
  buildMoneySettingsFormSchema,
  type MoneySettingsFormValues,
} from '@/app/(protected)/shared/settlement-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { GroupMoneySettings } from '@/lib/api/group-settlements';
import { SPLIT_METHODS } from '@/lib/constants/shared-expenses';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface GroupMoneySettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  settings: GroupMoneySettings;
  onSuccess: () => void;
}

/*
 * The two standards a group holds itself to when it spends together.
 *
 * Admin-only, which is the API's rule and the right one: setting the standard is management, not
 * money movement — every member still records expenses and payments. Nothing here grants any
 * additional visibility, in keeping with V2.
 *
 * Auto-finalise is D28's near-zero-friction path for a couple: the payee's confirmation is the trust
 * anchor for real money, and a two-person group that trusts itself can skip the round trip. It is
 * offered to any group rather than gated on member count — the API does not gate it, and a household
 * that wants it is not wrong to.
 */
export function GroupMoneySettingsDialog({
  open,
  onOpenChange,
  groupId,
  settings,
  onSuccess,
}: GroupMoneySettingsDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildMoneySettingsFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const toValues = (entity: GroupMoneySettings | undefined): MoneySettingsFormValues => ({
    defaultSplitMethod: entity?.defaultSplitMethod ?? 'equal',
    autoFinaliseSettlements: entity?.autoFinaliseSettlements ?? false,
  });

  const form = useForm<MoneySettingsFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(settings),
  });

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: settings,
    toValues,
    onSuccess,
  });

  async function onSubmit(values: MoneySettingsFormValues) {
    await submitWithLifecycle(
      () => updateGroupMoneySettings(groupId, values),
      t('moneySettings.success'),
      t('moneySettings.error'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('moneySettings.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('moneySettings.description')}</DialogDescription>

        <Form {...form}>
          <form
            id="money-settings-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="defaultSplitMethod"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('moneySettings.defaultSplit.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value}
                      onValueChange={field.onChange}
                      className="w-full"
                      options={SPLIT_METHODS.map((method) => ({
                        value: method,
                        label: t(`expenses.split.methods.${method}`),
                      }))}
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('moneySettings.defaultSplit.hint')}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="autoFinaliseSettlements"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-start justify-between gap-x-3">
                    <div className="flex flex-col gap-y-1">
                      <FormLabel>{t('moneySettings.autoFinalise.label')}</FormLabel>
                      <p className="text-paragraph-xs text-muted-foreground">
                        {t('moneySettings.autoFinalise.hint')}
                      </p>
                    </div>
                    <FormControl>
                      <Switch blue checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </div>
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
          <Button
            blue
            type="submit"
            form="money-settings-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('moneySettings.cta')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
