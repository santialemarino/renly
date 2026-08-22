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
import { addGroupMember, updateGroupMember } from '@/app/(protected)/shared/group-actions';
import {
  buildGroupMemberFormSchema,
  type GroupMemberFormValues,
} from '@/app/(protected)/shared/group-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FormCombobox } from '@/components/form-combobox';
import type { GroupMember } from '@/lib/api/groups';
import { GROUP_ROLES } from '@/lib/constants/groups';
import { useEntityFormDialog } from '@/lib/hooks/use-entity-form-dialog';

interface GroupMemberFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groupId: number;
  member?: GroupMember;
  onSuccess: () => void;
}

/*
 * Adds a name-only seat, or edits an existing one. Creating a member and inviting them are separate on
 * purpose: someone who will never use Renly still needs a real seat for their share of everything to
 * attach to, so adding a person never assumes an email exists.
 */
export function GroupMemberFormDialog({
  open,
  onOpenChange,
  groupId,
  member,
  onSuccess,
}: GroupMemberFormDialogProps) {
  const t = useTranslations('shared');
  const tCommon = useTranslations('common');

  const schema = useMemo(
    () => buildGroupMemberFormSchema(tCommon('form.errors.required')),
    [tCommon],
  );

  const form = useForm<GroupMemberFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { displayName: '', role: 'member' },
  });

  const isEdit = !!member;

  const { submitWithLifecycle } = useEntityFormDialog({
    open,
    onOpenChange,
    form,
    entity: member,
    toValues: (m) => ({ displayName: m?.displayName ?? '', role: m?.role ?? 'member' }),
    onSuccess,
  });

  const roleOptions = GROUP_ROLES.map((role) => ({
    value: role,
    label: t(`roles.${role}`),
    // A ReactNode, not a render function — the option row shows the role plus what it actually
    // grants, because "admin" is the one word in this app people assume means "can see everything".
    render: (
      <span className="flex flex-col gap-y-0.5">
        <span>{t(`roles.${role}`)}</span>
        <span className="text-paragraph-xs text-muted-foreground">{t(`roleHints.${role}`)}</span>
      </span>
    ),
  }));

  async function onSubmit(values: GroupMemberFormValues) {
    await submitWithLifecycle(
      () =>
        isEdit ? updateGroupMember(groupId, member.id, values) : addGroupMember(groupId, values),
      t(isEdit ? 'members.form.updateSuccess' : 'members.form.createSuccess'),
      t('members.form.saveError'),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t('members.form.titleEdit') : t('members.form.titleCreate')}
          </DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {isEdit ? t('members.form.descriptionEdit') : t('members.form.descriptionCreate')}
        </DialogDescription>

        <Form {...form}>
          <form
            id="group-member-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="displayName"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('members.form.displayName.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('members.form.displayName.placeholder')} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('members.form.role.label')}</FormLabel>
                  <FormControl>
                    <FormCombobox
                      value={field.value ?? ''}
                      onValueChange={field.onChange}
                      options={roleOptions}
                      placeholder={t('members.form.role.placeholder')}
                      className="w-full"
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
          <Button
            blue
            type="submit"
            form="group-member-form"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
