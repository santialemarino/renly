'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { signIn } from 'next-auth/react';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

import { Button, Input } from '@repo/ui/components';
import { PasswordMeter } from '@/app/(auth)/_components/password-meter';
import { signupFormSchema, type SignupFormData } from '@/app/(auth)/signup/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { ROUTES } from '@/config/routes';
import { EmailTakenError, registerRequest } from '@/lib/auth-api';
import {
  PASSWORD_CONTAINS_LOWERCASE_REGEX,
  PASSWORD_CONTAINS_NUMBER_REGEX,
  PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX,
  PASSWORD_CONTAINS_UPPERCASE_REGEX,
  PASSWORD_MIN_LENGTH,
} from '@/lib/constants/form';

const REDIRECT_DELAY_MS = 1500;

interface SignupFormProps {
  onSuccess: () => void;
  onError: () => void;
}

export function SignupForm({ onSuccess, onError }: SignupFormProps) {
  const t = useTranslations('signup');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const form = useForm<SignupFormData>({
    defaultValues: { name: '', email: '', password: '', confirmPassword: '' },
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    resolver: zodResolver(signupFormSchema(tCommon)),
  });

  const password = useWatch({ control: form.control, name: 'password' }) ?? '';

  const passingChecks = useMemo(
    () => ({
      characters: password.length >= PASSWORD_MIN_LENGTH,
      uppercase: PASSWORD_CONTAINS_UPPERCASE_REGEX.test(password),
      lowercase: PASSWORD_CONTAINS_LOWERCASE_REGEX.test(password),
      number: PASSWORD_CONTAINS_NUMBER_REGEX.test(password),
      special: PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX.test(password),
    }),
    [password],
  );

  const onSubmit = async (data: SignupFormData) => {
    try {
      await registerRequest({ name: data.name, email: data.email, password: data.password });

      const res = await signIn('credentials', {
        email: data.email,
        password: data.password,
        redirect: false,
        callbackUrl: ROUTES.home,
      });

      if (res?.ok) {
        onSuccess();
        await new Promise((resolve) => setTimeout(resolve, REDIRECT_DELAY_MS));
        router.push(ROUTES.home);
      } else {
        onError();
        form.setError('root', { message: tCommon('form.errors.serverError') });
      }
    } catch (err) {
      onError();
      if (err instanceof EmailTakenError) {
        form.setError('email', { message: t('form.errors.emailTaken') });
      } else {
        form.setError('root', { message: tCommon('form.errors.serverError') });
      }
    }
  };

  return (
    <Form {...form}>
      <form
        className="flex flex-col px-6 gap-y-6"
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
      >
        <div className="flex flex-col gap-y-5">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('form.name.label')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="text"
                    autoComplete="name"
                    placeholder={t('form.name.placeholder')}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

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
                    autoComplete="new-password"
                    placeholder={t('form.password.placeholder')}
                    blueEye
                  />
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
                <FormLabel>{t('form.confirmPassword.label')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="password"
                    autoComplete="new-password"
                    placeholder={t('form.confirmPassword.placeholder')}
                    blueEye
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {form.formState.errors.root && (
          <p className="text-paragraph-sm text-destructive text-center">
            {form.formState.errors.root.message}
          </p>
        )}

        <Button blue type="submit" size="lg" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
        </Button>
      </form>
    </Form>
  );
}
