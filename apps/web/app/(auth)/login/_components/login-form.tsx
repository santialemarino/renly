'use client';

import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { signIn } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

import { Button, Checkbox, Input } from '@repo/ui/components';
import { loginFormSchema, type LoginFormData } from '@/app/(auth)/login/form-schema';
import { seedLocalizationCookies } from '@/app/(auth)/login/login-actions';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { decodeApiError, resolveApiError } from '@/lib/i18n/api-errors';

interface LoginFormProps {
  // Where to land after a successful login. Already validated by the page against the app's own
  // routes, so it is used as-is here; null is the ordinary case and lands on the dashboard.
  nextPath?: string | null;
}

export function LoginForm({ nextPath }: LoginFormProps) {
  const t = useTranslations('login');
  const tCommon = useTranslations('common');
  const tApiErrors = useTranslations('apiErrors');
  // Holds the submit button in its loading state while the post-login document loads.
  const [redirecting, setRedirecting] = useState(false);
  const form = useForm<LoginFormData>({
    defaultValues: {
      email: '',
      password: '',
      rememberMe: false,
    },
    resolver: zodResolver(loginFormSchema(tCommon)),
  });
  const pending = form.formState.isSubmitting || redirecting;

  const onSubmit = async (data: LoginFormData) => {
    try {
      const res = await signIn('credentials', {
        email: data.email,
        password: data.password,
        rememberMe: data.rememberMe,
        redirect: false,
      });

      if (res?.error) {
        // A refusal the API coded (a rate limit) arrives packed into the sign-in code; anything else
        // from the credentials provider is a wrong email or password.
        const apiError = decodeApiError(res.code);
        const message = apiError
          ? resolveApiError(tApiErrors, apiError, tCommon('form.errors.serverError'))
          : res.error === 'CredentialsSignin'
            ? t('form.errors.invalid')
            : tCommon('form.errors.serverError');
        form.setError('password', { message });
        return;
      }

      /*
       * A full document load, not `router.push`: a soft navigation keeps the root layout — and with it
       * the next-intl provider holding the login page's messages — so a user whose stored language
       * differs from this browser's would see the app in the wrong language until something refreshed
       * it. The new document renders in the signed-in user's language from its first paint.
       */
      setRedirecting(true);
      // Best effort: should it fail, the document still renders in the pin and the layout seeds them.
      await seedLocalizationCookies().catch(() => {});
      window.location.assign(nextPath ?? ROUTES.home);
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
                  <Input
                    {...field}
                    type="email"
                    autoComplete="email"
                    placeholder={t('form.email.placeholder')}
                    data-testid="login-email-input"
                  />
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
                    passwordToggleLabel={tCommon('form.togglePassword')}
                    autoComplete="current-password"
                    placeholder={t('form.password.placeholder')}
                    blueEye
                    data-testid="login-password-input"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex items-center justify-between">
            <FormField
              control={form.control}
              name="rememberMe"
              render={({ field }) => (
                <FormItem className="flex-row items-center gap-x-2">
                  <FormControl>
                    <Checkbox blue checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                  <FormLabel className="cursor-pointer text-paragraph-sm text-muted-foreground">
                    {t('form.rememberMe')}
                  </FormLabel>
                </FormItem>
              )}
            />
            <InlineLink href={ROUTES.auth.forgotPassword}>{t('form.forgotPassword')}</InlineLink>
          </div>
        </div>

        <Button blue type="submit" size="lg" disabled={pending} data-testid="login-submit">
          {pending ? t('form.cta.loading') : t('form.cta.label')}
        </Button>
      </form>
    </Form>
  );
}
