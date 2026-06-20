'use client';

import { useState } from 'react';
import { MailCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { AuthLink } from '@/app/(auth)/_components/auth-link';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
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
    <AuthStatusScreen
      icon={MailCheck}
      tone="info"
      title={t('checkEmail.title')}
      description={t('checkEmail.description', { email })}
    >
      <div className="flex flex-col items-center gap-y-3">
        {resent ? (
          <p className="text-paragraph-sm-medium text-green-600">{t('checkEmail.resent')}</p>
        ) : (
          <Button variant="outline" size="sm" onClick={handleResend} disabled={resending}>
            {resending ? t('checkEmail.resending') : t('checkEmail.resend')}
          </Button>
        )}
        <AuthLink href={ROUTES.auth.login}>{t('checkEmail.backToLogin')}</AuthLink>
      </div>
    </AuthStatusScreen>
  );
}
