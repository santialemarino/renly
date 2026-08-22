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
import { createGroup, updateGroup } from '@/app/(protected)/shared/group-actions';
import {
  buildGroupFormSchema,
  type GroupFormValues,
} from '@/app/(protected)/shared/group-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { Group } from '@/lib/api/groups';
import { GROUP_KINDS } from '@/lib/constants/groups';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface GroupFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group?: Group;
  onSuccess: () => void;
}

export function GroupFormDialog({ open, onOpenChange, group, onSuccess }: GroupFormDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => buildGroupFormSchema(tCommon('form.errors.required')), [tCommon]);

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', kind: undefined, displayName: '' },
  });

  const isEdit = !!group;

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: group,
    toValues: (g) => ({
      name: g?.name ?? '',
      kind: (g?.kind ?? undefined) as GroupFormValues['kind'],
      displayName: '',
    }),
    onSuccess,
  });

  const kindOptions = GROUP_KINDS.map((kind) => ({
    value: kind,
    label: tCommon(`groupKinds.${kind}`),
  }));

  async function onSubmit(values: GroupFormValues) {
    await submitWithLifecycle(
      () => (isEdit ? updateGroup(group.id, values) : createGroup(values)),
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
        <DialogDescription>
          {isEdit ? t('form.descriptionEdit') : t('form.descriptionCreate')}
        </DialogDescription>

        <Form {...form}>
          <form
            id="group-form"
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

            <FormField
              control={form.control}
              name="kind"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('form.kind.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={kindOptions}
                      placeholder={t('form.kind.placeholder')}
                      className="w-full"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Only on create: the creator's own seat is renamed from the roster afterwards, like
                anyone else's, so offering it here too would be two controls for one field. */}
            {!isEdit && (
              <FormField
                control={form.control}
                name="displayName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('form.displayName.label')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('form.displayName.placeholder')} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="group-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
