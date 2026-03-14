'use client';

import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@repo/ui/components';
import { LoginForm } from '@/app/(auth)/login/_components/login-form';
import { ROUTES } from '@/config/routes';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: 0.25 },
};

export function LoginCard() {
  const t = useTranslations('login');

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        <CardHeader>
          <CardTitle className="text-heading-4 text-center text-blue-800">{t('title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
        <CardFooter className="justify-center gap-x-1 text-paragraph-sm text-muted-foreground">
          <span>{t('form.signup.title')}</span>
          <a
            href={ROUTES.auth.signup}
            className="hover:underline text-paragraph-sm-medium text-blue-700"
          >
            {t('form.signup.cta')}
          </a>
        </CardFooter>
      </Card>
    </motion.div>
  );
}
