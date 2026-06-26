'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';

import { Button, Input } from '@repo/ui/components';
import { changePasswordAction } from '@/app/(protected)/account/account-actions';
import {
  changePasswordSchema,
  type ChangePasswordData,
} from '@/app/(protected)/account/form-schemas';
import { userSignOut } from '@/auth';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { PasswordMeter } from '@/components/password-meter';
import { SectionHeader } from '@/components/section-header';
import { LOGIN_ROUTE } from '@/config/routes';
import {
  PASSWORD_CONTAINS_LOWERCASE_REGEX,
  PASSWORD_CONTAINS_NUMBER_REGEX,
  PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX,
  PASSWORD_CONTAINS_UPPERCASE_REGEX,
  PASSWORD_MIN_LENGTH,
} from '@/lib/constants/form';

export function ChangePasswordSection() {
  const t = useTranslations('account');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const form = useForm<ChangePasswordData>({
    defaultValues: { currentPassword: '', newPassword: '', confirmPassword: '' },
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    resolver: zodResolver(changePasswordSchema(tCommon)),
  });

  const newPassword = useWatch({ control: form.control, name: 'newPassword' }) ?? '';

  const passingChecks = useMemo(
    () => ({
      characters: newPassword.length >= PASSWORD_MIN_LENGTH,
      uppercase: PASSWORD_CONTAINS_UPPERCASE_REGEX.test(newPassword),
      lowercase: PASSWORD_CONTAINS_LOWERCASE_REGEX.test(newPassword),
      number: PASSWORD_CONTAINS_NUMBER_REGEX.test(newPassword),
      special: PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX.test(newPassword),
    }),
    [newPassword],
  );

  const onSubmit = async (data: ChangePasswordData) => {
    const result = await changePasswordAction(data.currentPassword, data.newPassword);
    if (result.error === 'invalid_password') {
      form.setError('currentPassword', { message: t('password.errors.invalidCurrent') });
      return;
    }
    if (result.error === 'password_rejected') {
      form.setError('newPassword', { message: t('password.errors.rejected') });
      return;
    }
    if (result.error) {
      toast.error(tCommon('form.errors.serverError'));
      return;
    }
    // Changing the password bumped session_epoch server-side, so this session's token is now
    // invalid — sign out and send the user to log in again with the new password.
    toast.success(t('password.success'));
    await userSignOut();
    router.push(LOGIN_ROUTE);
  };

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('password.title')} description={t('password.description')} />

      <Form {...form}>
        <form className="flex flex-col gap-y-5" onSubmit={form.handleSubmit(onSubmit)} noValidate>
          <FormField
            control={form.control}
            name="currentPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('password.currentLabel')}</FormLabel>
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

          <FormField
            control={form.control}
            name="newPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('password.newLabel')}</FormLabel>
                <FormControl>
                  <Input {...field} type="password" autoComplete="new-password" surface blueEye />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <PasswordMeter
            passingChecks={passingChecks}
            showErrors={form.formState.submitCount > 0}
          />

          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('password.confirmLabel')}</FormLabel>
                <FormControl>
                  <Input {...field} type="password" autoComplete="new-password" surface blueEye />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button blue type="submit" className="self-start" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('password.cta.loading') : t('password.cta.label')}
          </Button>
        </form>
      </Form>
    </section>
  );
}
