'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Input } from '@repo/ui/components';
import { changeNameAction } from '@/app/(protected)/account/account-actions';
import {
  changeNameSchema,
  NAME_MAX_LENGTH,
  type ChangeNameData,
} from '@/app/(protected)/account/form-schemas';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { SectionHeader } from '@/components/section-header';

interface ChangeNameSectionProps {
  currentName: string;
}

// The account's display name. Groups name their members themselves, so a seat keeps the name its group
// gave it; this is the name the account itself goes by.
export function ChangeNameSection({ currentName }: ChangeNameSectionProps) {
  const t = useTranslations('account');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const form = useForm<ChangeNameData>({
    defaultValues: { name: currentName },
    resolver: zodResolver(
      changeNameSchema(tCommon, t('name.errors.tooLong', { max: NAME_MAX_LENGTH })),
    ),
  });

  // After a save the page re-reads the name; the field follows it.
  useEffect(() => {
    form.reset({ name: currentName });
  }, [currentName, form]);

  const onSubmit = async (data: ChangeNameData) => {
    const result = await changeNameAction(data.name);
    if (result.error) {
      toast.error(tCommon('form.errors.serverError'));
      return;
    }
    toast.success(t('name.success'));
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
