'use client';

import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { signIn } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

import { Button, Input } from '@repo/ui/components';
import { loginFormSchema, type LoginFormData } from '@/app/(auth)/login/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { ROUTES } from '@/config/routes';

export function LoginForm() {
  const t = useTranslations('login');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const form = useForm<LoginFormData>({
    defaultValues: {
      email: '',
      password: '',
    },
    resolver: zodResolver(loginFormSchema(tCommon)),
  });

  const onSubmit = async (data: LoginFormData) => {
    try {
      const res = await signIn('credentials', {
        email: data.email,
        password: data.password,
        redirect: false,
      });

      if (res?.error) {
        const message =
          res.error === 'CredentialsSignin'
            ? t('form.errors.invalid')
            : tCommon('form.errors.serverError');
        form.setError('password', { message });
        return;
      }

      router.push(ROUTES.home);
    } catch {
      form.setError('password', { message: tCommon('form.errors.serverError') });
    }
  };

  return (
    <Form {...form}>
      <form
        className="flex flex-col px-6 gap-y-8"
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
      >
        <div className="flex flex-col gap-y-5">
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('form.email.label')}</FormLabel>
                <FormControl>
                  <Input {...field} type="email" placeholder={t('form.email.placeholder')} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('form.password.label')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="password"
                    placeholder={t('form.password.placeholder')}
                    blueEye
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <Button blue type="submit" size="lg" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
        </Button>
      </form>
    </Form>
  );
}
