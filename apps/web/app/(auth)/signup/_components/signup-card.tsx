'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@repo/ui/components';
import { CheckEmailNotice } from '@/app/(auth)/_components/check-email-notice';
import { SignupForm } from '@/app/(auth)/signup/_components/signup-form';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { requestVerificationEmail } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: ANIMATION_DEFAULT },
};

interface SignupCardProps {
  // When set (invite-only mode via a valid link), the email is locked to the invited address and the
  // token is submitted with the registration. Both null in open mode.
  lockedEmail?: string | null;
  inviteToken?: string | null;
}

export function SignupCard({ lockedEmail = null, inviteToken = null }: SignupCardProps) {
  const t = useTranslations('signup');
  const tCommon = useTranslations('common');
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

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
              <SignupForm
                lockedEmail={lockedEmail}
                inviteToken={inviteToken}
                onSuccess={(email) => setSubmittedEmail(email)}
                onError={() => setSubmittedEmail(null)}
              />
            </CardContent>
            <CardFooter className="justify-center gap-x-1 px-6 text-paragraph-sm text-muted-foreground">
              <span>{t('form.login.title')}</span>
              <InlineLink href={ROUTES.auth.login}>{t('form.login.cta')}</InlineLink>
            </CardFooter>
          </Card>
        </motion.div>
      ) : (
        <motion.div key="check-email" className="w-full max-w-auth-form" {...FADE_PROPS}>
          <Card>
            <CheckEmailNotice
              title={tCommon('checkEmail.title')}
              description={tCommon('checkEmail.description', { email: submittedEmail })}
              onResend={() => requestVerificationEmail(submittedEmail)}
            />
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
