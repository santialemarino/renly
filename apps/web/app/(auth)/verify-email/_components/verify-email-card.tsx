'use client';

import { useEffect, useRef, useState } from 'react';
import { CircleCheck, CircleX } from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@repo/ui/components';
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

  const isError = status === 'error';
  const isLoading = status === 'loading';

  return (
    <motion.div className="w-full max-w-auth-form" {...FADE_PROPS}>
      <Card>
        <CardHeader>
          <CardTitle className="text-heading-4 text-center text-blue-800">{t('title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-2 gap-y-4 text-center">
            {isLoading && (
              <>
                <div className="size-10 rounded-full border-4 border-muted border-t-blue-600 animate-spin" />
                <p className="text-paragraph-sm text-muted-foreground">{t('loading')}</p>
              </>
            )}
            {!isLoading && !isError && <CircleCheck className="size-12 text-green-500" />}
            {isError && <CircleX className="size-12 text-destructive" />}
            {!isLoading && (
              <p className="text-paragraph-sm text-muted-foreground">{t(`status.${status}`)}</p>
            )}
          </div>
        </CardContent>
        {!isLoading && (
          <CardFooter className="justify-center text-paragraph-sm text-muted-foreground">
            <a
              href={ROUTES.auth.login}
              className="hover:underline text-paragraph-sm-medium text-blue-700"
            >
              {t('goToLogin')}
            </a>
          </CardFooter>
        )}
      </Card>
    </motion.div>
  );
}
