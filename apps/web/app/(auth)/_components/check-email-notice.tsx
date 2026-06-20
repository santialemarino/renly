'use client';

import { useEffect, useState } from 'react';
import { MailCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { AuthLink } from '@/app/(auth)/_components/auth-link';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
import { ROUTES } from '@/config/routes';
import { requestVerificationEmail } from '@/lib/auth-api';

// Seconds the user must wait before requesting another email (standard anti-abuse cooldown).
const RESEND_COOLDOWN_SECONDS = 30;

interface CheckEmailNoticeProps {
  email: string;
}

// Post-signup / pre-login screen: tells the user to open the emailed message and lets them resend
// it on a cooldown (so they can retry if it didn't arrive). The resend response is uniform (never
// reveals account state), so it always reports sent.
export function CheckEmailNotice({ email }: CheckEmailNoticeProps) {
  const t = useTranslations('common');
  const [resending, setResending] = useState(false);
  const [sent, setSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  const resendLabel = resending
    ? t('checkEmail.resending')
    : cooldown > 0
      ? t('checkEmail.resendIn', { seconds: cooldown })
      : t('checkEmail.resend');

  // Tick the cooldown down to zero, re-enabling the resend button.
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function handleResend() {
    setResending(true);
    try {
      await requestVerificationEmail(email);
    } catch {
      // Uniform behaviour: surface "sent" regardless so account existence isn't revealed.
    } finally {
      setSent(true);
      setCooldown(RESEND_COOLDOWN_SECONDS);
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
        {sent && (
          <p className="text-paragraph-sm-medium text-green-600 animate-in fade-in duration-300">
            {t('checkEmail.resent')}
          </p>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={handleResend}
          disabled={resending || cooldown > 0}
        >
          {resendLabel}
        </Button>
        <AuthLink href={ROUTES.auth.login}>{t('checkEmail.backToLogin')}</AuthLink>
      </div>
    </AuthStatusScreen>
  );
}
