'use client';

import { useState } from 'react';
import { MailCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { requestVerificationEmail } from '@/lib/auth-api';

interface CheckEmailNoticeProps {
  email: string;
}

// Post-signup / pre-login screen: tells the user to click the verification link and lets them
// resend it. The resend response is uniform (never reveals account state), so it always reports sent.
export function CheckEmailNotice({ email }: CheckEmailNoticeProps) {
  const t = useTranslations('common');
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  async function handleResend() {
    setResending(true);
    try {
      await requestVerificationEmail(email);
    } catch {
      // Uniform behaviour: surface "sent" regardless so account existence isn't revealed.
    } finally {
      setResent(true);
      setResending(false);
    }
  }

  return (
    <div className="flex flex-col items-center justify-center px-6 py-6 gap-y-6">
      <div className="relative flex items-center justify-center">
        <div className="absolute size-24 rounded-full bg-blue-50" />
        <MailCheck className="relative size-16 text-blue-600 animate-in zoom-in-50 duration-500" />
      </div>

      <div className="flex flex-col items-center gap-y-2 text-center">
        <p className="text-paragraph-semibold text-foreground">{t('checkEmail.title')}</p>
        <p className="text-paragraph-sm text-muted-foreground">
          {t('checkEmail.description', { email })}
        </p>
      </div>

      <div className="flex flex-col w-full items-center gap-y-3">
        {resent ? (
          <p className="text-paragraph-sm-medium text-green-600">{t('checkEmail.resent')}</p>
        ) : (
          <Button variant="outline" size="sm" onClick={handleResend} disabled={resending}>
            {resending ? t('checkEmail.resending') : t('checkEmail.resend')}
          </Button>
        )}
        <a
          href={ROUTES.auth.login}
          className="hover:underline text-paragraph-sm-medium text-blue-700"
        >
          {t('checkEmail.backToLogin')}
        </a>
      </div>
    </div>
  );
}
