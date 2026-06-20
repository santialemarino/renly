'use client';

import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { MailCheck } from 'lucide-react';
import { motion } from 'motion/react';
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
import {
  forgotPasswordFormSchema,
  type ForgotPasswordFormData,
} from '@/app/(auth)/forgot-password/form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { ROUTES } from '@/config/routes';
import { forgotPasswordRequest } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: ANIMATION_DEFAULT },
};

export function ForgotPasswordCard() {
  const t = useTranslations('forgotPassword');
  const tCommon = useTranslations('common');
  const [submitted, setSubmitted] = useState(false);

  const form = useForm<ForgotPasswordFormData>({
    defaultValues: { email: '' },
    resolver: zodResolver(forgotPasswordFormSchema(tCommon)),
  });

  const onSubmit = async (data: ForgotPasswordFormData) => {
    try {
      await forgotPasswordRequest(data.email);
      // Uniform: always show the "sent" state so account existence isn't revealed.
      setSubmitted(true);
    } catch {
      form.setError('root', { message: tCommon('form.errors.serverError') });
    }
  };

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        <CardHeader>
          <CardTitle className="text-heading-4 text-center text-blue-800">{t('title')}</CardTitle>
        </CardHeader>

        {submitted ? (
          <CardContent>
            <div className="flex flex-col items-center justify-center py-2 gap-y-4 text-center">
              <MailCheck className="size-12 text-blue-600" />
              <p className="text-paragraph-sm text-muted-foreground">{t('sent')}</p>
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
                <p className="text-paragraph-sm text-muted-foreground">{t('description')}</p>
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
