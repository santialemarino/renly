'use client';

import { useEffect, useTransition } from 'react';
import { useRouter } from 'next/navigation';
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
import {
  createCollection,
  updateCollection,
} from '@/app/(protected)/collections/collections-actions';
import {
  buildCollectionFormSchema,
  type CollectionFormValues,
} from '@/app/(protected)/collections/collections-form-schema';
import { ComboboxMultiSelect } from '@/components/combobox-multi-select';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { LocaleAmountInput } from '@/components/locale-amount-input';
import type { InvestmentCollection } from '@/lib/api/collections';

interface CollectionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collection?: InvestmentCollection;
  investments: { id: number; name: string }[];
  onSuccess?: () => void;
}

export function CollectionFormDialog({
  open,
  onOpenChange,
  collection,
  investments,
  onSuccess,
}: CollectionFormDialogProps) {
  const t = useTranslations('collections');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const isEdit = !!collection;

  const schema = buildCollectionFormSchema(
    tCommon('form.errors.required'),
    t('form.targetPercentage.invalidRange'),
  );
  const form = useForm<CollectionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: collection?.name ?? '',
      targetPercentage:
        collection?.targetPercentage != null ? String(collection.targetPercentage) : '',
      investmentIds: collection?.investmentIds ?? [],
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        name: collection?.name ?? '',
        targetPercentage:
          collection?.targetPercentage != null ? String(collection.targetPercentage) : '',
        investmentIds: collection?.investmentIds ?? [],
      });
    }
  }, [open, collection, form]);

  const selectedIds = form.watch('investmentIds') ?? [];

  function toggleInvestment(id: number) {
    const current = form.getValues('investmentIds') ?? [];
    form.setValue(
      'investmentIds',
      current.includes(id) ? current.filter((i) => i !== id) : [...current, id],
    );
  }

  function onSubmit(values: CollectionFormValues) {
    startTransition(async () => {
      try {
        if (isEdit) {
          await updateCollection(collection.id, values);
          toast.success(t('form.success.edit'));
        } else {
          await createCollection(values);
          toast.success(t('form.success.create'));
        }
        if (onSuccess) {
          onSuccess();
        } else {
          router.refresh();
        }
        onOpenChange(false);
      } catch {
        toast.error(isEdit ? t('form.error.edit') : t('form.error.create'));
      }
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('form.editTitle') : t('form.createTitle')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="group-form"
            noValidate
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-y-4"
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

            <FormField
              control={form.control}
              name="targetPercentage"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('form.targetPercentage.label')}</FormLabel>
                  <FormControl>
                    <LocaleAmountInput
                      {...field}
                      maxDecimals={2}
                      placeholder={t('form.targetPercentage.placeholder')}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex flex-col gap-y-2">
              <FormLabel>{t('form.investments.label')}</FormLabel>
              <ComboboxMultiSelect
                items={investments.map((inv) => ({ id: inv.id, label: inv.name }))}
                selectedIds={selectedIds}
                onToggle={toggleInvestment}
                placeholder={t('form.investments.placeholder')}
                searchPlaceholder={t('form.investments.placeholder')}
                emptyMessage={t('form.investments.empty')}
                showChips
              />
            </div>
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="group-form" disabled={isPending}>
            {isPending ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
