'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@repo/ui/components';
import { RedirectingScreen } from '@/app/(auth)/signup/_components/redirecting-screen';
import { SignupForm } from '@/app/(auth)/signup/_components/signup-form';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: ANIMATION_DEFAULT },
};

export function SignupCard() {
  const t = useTranslations('signup');
  const [isRedirecting, setIsRedirecting] = useState(false);

  return (
    <AnimatePresence mode="wait">
      {!isRedirecting ? (
        <motion.div key="form" {...FADE_PROPS} className="w-full max-w-auth-form">
          <Card>
            <CardHeader>
              <CardTitle className="text-heading-4 text-center text-blue-800">
                {t('title')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SignupForm
                onSuccess={() => setIsRedirecting(true)}
                onError={() => setIsRedirecting(false)}
              />
            </CardContent>
            <CardFooter className="justify-center gap-x-1 text-paragraph-sm text-muted-foreground">
              <span>{t('form.login.title')}</span>
              <a
                href={ROUTES.auth.login}
                className="hover:underline text-paragraph-sm-medium text-blue-700"
              >
                {t('form.login.cta')}
              </a>
            </CardFooter>
          </Card>
        </motion.div>
      ) : (
        <motion.div key="redirecting" className="w-full max-w-auth-form" {...FADE_PROPS}>
          <Card>
            <RedirectingScreen
              title={t('redirecting.title')}
              description={t('redirecting.description')}
            />
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
