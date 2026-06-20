'use client';

import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { CircleCheck, CircleX } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
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
import { AuthLink } from '@/app/(auth)/_components/auth-link';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
import {
  resetPasswordFormSchema,
  type ResetPasswordFormData,
} from '@/app/(auth)/reset-password/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { PasswordMeter } from '@/components/password-meter';
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
  exit: { opacity: 0 },
  transition: { duration: ANIMATION_DEFAULT },
};

type Stage = 'form' | 'done' | 'error';

interface ResetPasswordCardProps {
  token: string | null;
}

export function ResetPasswordCard({ token }: ResetPasswordCardProps) {
  const t = useTranslations('resetPassword');
  const tCommon = useTranslations('common');
  // No token in the link → straight to the error screen; otherwise show the form.
  const [stage, setStage] = useState<Stage>(token ? 'form' : 'error');

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
      setStage('done');
    } catch (err) {
      if (err instanceof PasswordRejectedError) {
        form.setError('password', { message: t('form.errors.passwordRejected') });
      } else {
        // Invalid/expired token (or server error) — show the error screen with a way back.
        setStage('error');
      }
    }
  };

  return (
    <AnimatePresence mode="wait">
      {stage === 'done' ? (
        <motion.div key="done" {...FADE_PROPS} className="w-full max-w-auth-form">
          <Card>
            <AuthStatusScreen
              icon={CircleCheck}
              tone="success"
              title={t('successTitle')}
              description={t('success')}
            >
              <AuthLink href={ROUTES.auth.login}>{t('backToLogin')}</AuthLink>
            </AuthStatusScreen>
          </Card>
        </motion.div>
      ) : stage === 'error' ? (
        <motion.div key="error" {...FADE_PROPS} className="w-full max-w-auth-form">
          <Card>
            <AuthStatusScreen
              icon={CircleX}
              tone="error"
              title={t('errorTitle')}
              description={t('form.errors.invalidToken')}
            >
              <AuthLink href={ROUTES.auth.forgotPassword}>{t('requestNewLink')}</AuthLink>
            </AuthStatusScreen>
          </Card>
        </motion.div>
      ) : (
        <motion.div key="form" {...FADE_PROPS} className="w-full max-w-auth-form">
          <Card>
            <CardHeader>
              <CardTitle className="text-heading-4 text-center text-blue-800">
                {t('title')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Form {...form}>
                <form
                  className="flex flex-col px-6 gap-y-8"
                  onSubmit={form.handleSubmit(onSubmit)}
                  noValidate
                >
                  <div className="flex flex-col gap-y-5">
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

                  <Button blue type="submit" size="lg" disabled={form.formState.isSubmitting}>
                    {form.formState.isSubmitting ? t('form.cta.loading') : t('form.cta.label')}
                  </Button>
                </form>
              </Form>
            </CardContent>
            <CardFooter className="justify-center px-6 text-paragraph-sm text-muted-foreground">
              <AuthLink href={ROUTES.auth.login}>{t('backToLogin')}</AuthLink>
            </CardFooter>
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
