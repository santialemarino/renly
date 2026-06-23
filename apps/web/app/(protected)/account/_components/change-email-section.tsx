'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Input } from '@repo/ui/components';
import { SectionHeader } from '@/app/(protected)/account/_components/section-header';
import { changeEmailAction } from '@/app/(protected)/account/account-actions';
import { changeEmailSchema, type ChangeEmailData } from '@/app/(protected)/account/form-schemas';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';

interface ChangeEmailSectionProps {
  currentEmail: string;
}

export function ChangeEmailSection({ currentEmail }: ChangeEmailSectionProps) {
  const t = useTranslations('account');
  const tCommon = useTranslations('common');

  const form = useForm<ChangeEmailData>({
    defaultValues: { currentPassword: '', newEmail: '' },
    resolver: zodResolver(changeEmailSchema(tCommon)),
  });

  const onSubmit = async (data: ChangeEmailData) => {
    const result = await changeEmailAction(data.currentPassword, data.newEmail);
    if (result.error === 'invalid_password') {
      form.setError('currentPassword', { message: t('email.errors.invalidPassword') });
      return;
    }
    if (result.error) {
      toast.error(tCommon('form.errors.serverError'));
      return;
    }
    // Uniform: a confirmation link is sent to the new address (or a notice if it's already taken).
    toast.success(t('email.success', { email: data.newEmail }));
    form.reset();
  };

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader
        title={t('email.title')}
        description={t('email.current', { email: currentEmail })}
      />

      <Form {...form}>
        <form className="flex flex-col gap-y-5" onSubmit={form.handleSubmit(onSubmit)} noValidate>
          <FormField
            control={form.control}
            name="newEmail"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('email.newLabel')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="email"
                    autoComplete="email"
                    surface
                    placeholder={t('email.placeholder')}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="currentPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('email.passwordLabel')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="password"
                    autoComplete="current-password"
                    surface
                    blueEye
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button blue type="submit" className="self-start" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('email.cta.loading') : t('email.cta.label')}
          </Button>
        </form>
      </Form>
    </section>
  );
}
