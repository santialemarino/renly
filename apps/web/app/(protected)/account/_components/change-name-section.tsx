'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Checkbox, Input } from '@repo/ui/components';
import { changeNameAction } from '@/app/(protected)/account/account-actions';
import {
  changeNameSchema,
  NAME_MAX_LENGTH,
  type ChangeNameData,
} from '@/app/(protected)/account/form-schemas';
import { offersGroupRename, renameGroupSeatsOnSave } from '@/app/(protected)/account/rename-groups';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/form';
import { SectionHeader } from '@/components/section-header';
import type { GroupUsingAccountName } from '@/lib/api/me';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';

// The form's row gap (`gap-y-5`). The groups option pulls itself up by it and pads it back inside, so
// while it is closed it takes no gap at all and the Save button does not jump when it mounts.
const FORM_GAP_PX = 20;

interface ChangeNameSectionProps {
  currentName: string;
  groupsUsingName: GroupUsingAccountName[];
}

// The account's display name. Groups name their members themselves, so a seat keeps the name its group
// gave it; renaming the account can bring along the seats that still carry the current name, when the
// user asks for it.
export function ChangeNameSection({ currentName, groupsUsingName }: ChangeNameSectionProps) {
  const fmt = useFormatters();
  const t = useTranslations('account');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const form = useForm<ChangeNameData>({
    defaultValues: { name: currentName, renameGroupSeats: false },
    resolver: zodResolver(
      changeNameSchema(tCommon, t('name.errors.tooLong', { max: NAME_MAX_LENGTH })),
    ),
  });
  const draftName = useWatch({ control: form.control, name: 'name' });

  const groupCount = groupsUsingName.length;
  const offerGroups = offersGroupRename(draftName, currentName, groupCount);

  // After a save the page re-reads the name and the groups; the form follows, unticked.
  useEffect(() => {
    form.reset({ name: currentName, renameGroupSeats: false });
  }, [currentName, form]);

  const onSubmit = async (data: ChangeNameData) => {
    const renameGroupSeats = renameGroupSeatsOnSave(
      data.renameGroupSeats,
      offersGroupRename(data.name, currentName, groupCount),
    );
    const result = await changeNameAction(data.name, renameGroupSeats);
    if (result.error) {
      toast.error(tCommon('form.errors.serverError'));
      return;
    }
    toast.success(
      renameGroupSeats
        ? t('name.successWithGroups', { count: result.groupSeatsRenamed ?? 0 })
        : t('name.success'),
    );
    router.refresh();
  };

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('name.title')} description={t('name.description')} />

      <Form {...form}>
        <form className="flex flex-col gap-y-5" onSubmit={form.handleSubmit(onSubmit)} noValidate>
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('name.label')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    autoComplete="name"
                    maxLength={NAME_MAX_LENGTH}
                    surface
                    data-testid="account-name-input"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <AnimatePresence initial={false}>
            {offerGroups && (
              <motion.div
                key="rename-groups"
                initial={{ opacity: 0, height: 0, overflow: 'hidden' }}
                animate={{ opacity: 1, height: 'auto', overflow: 'visible' }}
                exit={{ opacity: 0, height: 0, overflow: 'hidden' }}
                transition={{ duration: ANIMATION_DEFAULT }}
                style={{ marginTop: -FORM_GAP_PX }}
                data-testid="account-name-groups"
              >
                <FormField
                  control={form.control}
                  name="renameGroupSeats"
                  render={({ field }) => (
                    <FormItem className="pt-5 gap-y-1">
                      <div className="flex items-center gap-x-2">
                        <FormControl>
                          <Checkbox
                            ref={field.ref}
                            name={field.name}
                            checked={field.value === true}
                            onCheckedChange={(checked) => field.onChange(checked === true)}
                            onBlur={field.onBlur}
                            data-testid="account-name-groups-checkbox"
                          />
                        </FormControl>
                        <FormLabel className="cursor-pointer text-paragraph-sm">
                          {t('name.groups.label', { count: groupCount })}
                        </FormLabel>
                      </div>
                      <FormDescription className="flex flex-col pl-6 gap-y-0.5 text-paragraph-xs">
                        <span>{t('name.groups.helper', { name: currentName })}</span>
                        <span data-testid="account-name-groups-list">
                          {t('name.groups.which', {
                            count: groupCount,
                            groups: fmt.list(groupsUsingName.map((group) => group.name)),
                          })}
                        </span>
                      </FormDescription>
                    </FormItem>
                  )}
                />
              </motion.div>
            )}
          </AnimatePresence>

          <Button
            blue
            type="submit"
            className="self-start"
            disabled={form.formState.isSubmitting || !form.formState.isDirty}
            data-testid="account-name-submit"
          >
            {form.formState.isSubmitting ? t('name.cta.loading') : t('name.cta.label')}
          </Button>
        </form>
      </Form>
    </section>
  );
}
