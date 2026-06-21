'use client';

import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';

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
import { CheckEmailNotice } from '@/app/(auth)/_components/check-email-notice';
import {
  forgotPasswordFormSchema,
  type ForgotPasswordFormData,
} from '@/app/(auth)/forgot-password/form-schema';
import {
  Form,
  FormControl,
  FormError,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/form';
import { ROUTES } from '@/config/routes';
import { forgotPasswordRequest } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: ANIMATION_DEFAULT },
};

export function ForgotPasswordCard() {
  const t = useTranslations('forgotPassword');
  const tCommon = useTranslations('common');
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  const form = useForm<ForgotPasswordFormData>({
    defaultValues: { email: '' },
    resolver: zodResolver(forgotPasswordFormSchema(tCommon)),
  });

  const onSubmit = async (data: ForgotPasswordFormData) => {
    try {
      await forgotPasswordRequest(data.email);
      // Uniform: always show the "sent" state so account existence isn't revealed.
      setSubmittedEmail(data.email);
    } catch {
      form.setError('root', { message: tCommon('form.errors.serverError') });
    }
  };

  return (
    <AnimatePresence mode="wait">
      {!submittedEmail ? (
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
                    <p className="text-paragraph-sm text-muted-foreground">{t('description')}</p>
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
                    <FormError message={form.formState.errors.root?.message} />
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
      ) : (
        <motion.div key="sent" {...FADE_PROPS} className="w-full max-w-auth-form">
          <Card>
            <CheckEmailNotice
              title={t('sentTitle')}
              description={t('sent', { email: submittedEmail })}
              onResend={() => forgotPasswordRequest(submittedEmail)}
            />
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
