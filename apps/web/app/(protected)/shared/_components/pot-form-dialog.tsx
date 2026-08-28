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
  Input,
} from '@repo/ui/components';
import { CurrencyCombobox } from '@/app/(protected)/_components/currency-combobox';
import { createPot, updatePot } from '@/app/(protected)/shared/pot-actions';
import { buildPotFormSchema, type PotFormValues } from '@/app/(protected)/shared/pot-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { Pot } from '@/lib/api/pots';
import { POT_VISIBILITIES } from '@/lib/constants/pots';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface PotFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  pot?: Pot;
  preferredCurrencies?: string[];
  onSuccess: () => void;
}

/*
 * Creating or renaming the container co-ownership attaches to. Admin-only at the API, so the callers
 * render it only for an admin.
 *
 * The base currency is asked for on create and absent on edit, because it is the unit of every figure
 * already recorded in the ledger — the API's update body has no such field, so offering it would be a
 * control whose value is silently discarded.
 */
export function PotFormDialog({
  open,
  onOpenChange,
  groupId,
  pot,
  preferredCurrencies,
  onSuccess,
}: PotFormDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildPotFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<PotFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', baseCurrency: '', visibility: 'members' },
  });

  const isEdit = !!pot;

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: pot,
    toValues: (p) => ({
      name: p?.name ?? '',
      baseCurrency: p?.baseCurrency ?? '',
      visibility: p?.visibility ?? 'members',
    }),
    onSuccess,
  });

  const visibilityOptions = POT_VISIBILITIES.map((visibility) => ({
    value: visibility,
    label: t(`pots.visibility.${visibility}`),
  }));

  async function onSubmit(values: PotFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updatePot(pot.id, values) : createPot(groupId, values)),
      t(isEdit ? 'pots.form.updateSuccess' : 'pots.form.createSuccess'),
      t('pots.form.saveError'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t('pots.form.titleEdit') : t('pots.form.titleCreate')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {isEdit ? t('pots.form.descriptionEdit') : t('pots.form.descriptionCreate')}
        </DialogDescription>

        <Form {...form}>
          <form
            id="pot-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('pots.form.name.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('pots.form.name.placeholder')} />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.form.name.hint')}
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Create only: changing it afterwards would restate every figure already in the ledger at
                a rate nobody chose, so the API's update body does not carry it. */}
            {!isEdit && (
              <FormField
                control={form.control}
                name="baseCurrency"
                render={({ field }) => (
                  <FormItem required>
                    <FormLabel>{t('pots.form.baseCurrency.label')}</FormLabel>
                    <FormControl>
                      <CurrencyCombobox
                        value={field.value || null}
                        exclude={[]}
                        preferredCurrencies={preferredCurrencies}
                        placeholder={t('pots.form.baseCurrency.placeholder')}
                        searchPlaceholder={t('pots.form.baseCurrency.searchPlaceholder')}
                        noResults={t('pots.form.baseCurrency.noResults')}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <p className="text-paragraph-xs text-muted-foreground">
                      {t('pots.form.baseCurrency.hint')}
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="visibility"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('pots.form.visibility.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={visibilityOptions}
                      placeholder={t('pots.form.visibility.placeholder')}
                      className="w-full"
                    />
                  </FormControl>
                  <p className="text-paragraph-xs text-muted-foreground">
                    {t('pots.form.visibility.hint')}
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
          <Button blue type="submit" form="pot-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
