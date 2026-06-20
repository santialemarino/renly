'use client';

import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { CircleCheck } from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm, useWatch } from 'react-hook-form';

import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
} from '@repo/ui/components';
import { PasswordMeter } from '@/app/(auth)/_components/password-meter';
import {
  resetPasswordFormSchema,
  type ResetPasswordFormData,
} from '@/app/(auth)/reset-password/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { ROUTES } from '@/config/routes';
import { PasswordRejectedError, resetPasswordRequest } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import {
  PASSWORD_CONTAINS_LOWERCASE_REGEX,
  PASSWORD_CONTAINS_NUMBER_REGEX,
  PASSWORD_CONTAINS_SPECIAL_CHARACTER_REGEX,
  PASSWORD_CONTAINS_UPPERCASE_REGEX,
  PASSWORD_MIN_LENGTH,
} from '@/lib/constants/form';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: ANIMATION_DEFAULT },
};

interface ResetPasswordCardProps {
  token: string | null;
}

export function ResetPasswordCard({ token }: ResetPasswordCardProps) {
  const t = useTranslations('resetPassword');
  const tCommon = useTranslations('common');
  const [done, setDone] = useState(false);

  const form = useForm<ResetPasswordFormData>({
    defaultValues: { password: '', confirmPassword: '' },
    mode: 'onSubmit',
    reValidateMode: 'onChange',
    resolver: zodResolver(resetPasswordFormSchema(tCommon)),
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

  const onSubmit = async (data: ResetPasswordFormData) => {
    if (!token) return;
    try {
      await resetPasswordRequest(token, data.password);
      setDone(true);
    } catch (err) {
      if (err instanceof PasswordRejectedError) {
        form.setError('password', { message: t('form.errors.passwordRejected') });
      } else {
        form.setError('root', { message: t('form.errors.invalidToken') });
      }
    }
  };

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        <CardHeader>
          <CardTitle className="text-heading-4 text-center text-blue-800">{t('title')}</CardTitle>
        </CardHeader>

        {done || !token ? (
          <CardContent>
            <div className="flex flex-col items-center justify-center py-2 gap-y-4 text-center">
              {done && <CircleCheck className="size-12 text-green-500" />}
              <p className="text-paragraph-sm text-muted-foreground">
                {done ? t('success') : t('form.errors.missingToken')}
              </p>
            </div>
          </CardContent>
        ) : (
          <CardContent>
            <Form {...form}>
              <form
                className="flex flex-col gap-y-6"
                onSubmit={form.handleSubmit(onSubmit)}
                noValidate
              >
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
          </CardContent>
        )}

        <CardFooter className="justify-center text-paragraph-sm text-muted-foreground">
          <a
            href={ROUTES.auth.login}
            className="hover:underline text-paragraph-sm-medium text-blue-700"
          >
            {t('backToLogin')}
          </a>
        </CardFooter>
      </Card>
    </motion.div>
  );
}
