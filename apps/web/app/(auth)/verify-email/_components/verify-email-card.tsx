'use client';

import { useEffect, useRef, useState } from 'react';
import { CircleCheck, CircleX } from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Card } from '@repo/ui/components';
import { AuthLink } from '@/app/(auth)/_components/auth-link';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
import { ROUTES } from '@/config/routes';
import { confirmEmailToken, type ConfirmEmailKind } from '@/lib/auth-api';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const FADE_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: ANIMATION_DEFAULT },
};

type Status = 'loading' | 'verified' | 'changed' | 'error';

const KIND_TO_STATUS: Record<ConfirmEmailKind, Status> = {
  email_verification: 'verified',
  email_change: 'changed',
};

interface VerifyEmailCardProps {
  token: string | null;
}

export function VerifyEmailCard({ token }: VerifyEmailCardProps) {
  const t = useTranslations('verifyEmail');
  const [status, setStatus] = useState<Status>(token ? 'loading' : 'error');
  // Guard against the effect running twice (React strict mode) consuming the single-use token twice.
  const startedRef = useRef(false);

  useEffect(() => {
    if (!token || startedRef.current) return;
    startedRef.current = true;
    confirmEmailToken(token)
      .then((kind) => setStatus(KIND_TO_STATUS[kind]))
      .catch(() => setStatus('error'));
  }, [token]);

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        {status === 'loading' ? (
          <div className="flex flex-col items-center px-6 gap-y-5 text-center">
            <div className="size-10 rounded-full border-4 border-muted border-t-blue-600 animate-spin" />
            <p className="text-paragraph-sm text-muted-foreground">{t('loading')}</p>
          </div>
        ) : (
          <AuthStatusScreen
            icon={status === 'error' ? CircleX : CircleCheck}
            tone={status === 'error' ? 'error' : 'success'}
            title={t(`status.${status}.title`)}
            description={t(`status.${status}.description`)}
          >
            <AuthLink href={ROUTES.auth.login}>{t('goToLogin')}</AuthLink>
          </AuthStatusScreen>
        )}
      </Card>
    </motion.div>
  );
}
