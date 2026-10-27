'use client';

import { useEffect, useState } from 'react';
import { MailCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { RateLimitedError } from '@/lib/auth-api';
import { resolveApiError } from '@/lib/i18n/api-errors';

// Seconds the user must wait before requesting another email (standard anti-abuse cooldown).
const RESEND_COOLDOWN_SECONDS = 30;

interface CheckEmailNoticeProps {
  title: string;
  description: string;
  onResend: () => Promise<void>;
}

// Post-submit "check your email" screen, shared by signup (verification) and forgot-password (reset):
// tells the user to open the emailed message and lets them resend it on a cooldown (so they can retry
// if it didn't arrive). The caller injects the title, description, and resend action; every resend
// response is uniform (never reveals account state), so it reports sent — unless the API rate-limited
// it, which says nothing about the account and is shown as itself.
export function CheckEmailNotice({ title, description, onResend }: CheckEmailNoticeProps) {
  const t = useTranslations('common');
  const tApiErrors = useTranslations('apiErrors');
  const [resending, setResending] = useState(false);
  const [sent, setSent] = useState(false);
  // The localized rate-limit message when the last resend was throttled, else null.
  const [limited, setLimited] = useState<string | null>(null);
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
    let throttled: string | null = null;
    try {
      await onResend();
    } catch (err) {
      // Uniform behaviour: surface "sent" regardless so account existence isn't revealed — except for
      // a rate limit, which is about this browser, not the account, and nothing was sent.
      if (err instanceof RateLimitedError) {
        throttled = resolveApiError(tApiErrors, err.apiError, t('form.errors.serverError'));
      }
    } finally {
      setLimited(throttled);
      setSent(throttled === null);
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setResending(false);
    }
  }

  return (
    <AuthStatusScreen icon={MailCheck} tone="info" title={title} description={description}>
      <div className="flex flex-col items-center gap-y-3">
        {sent && (
          <p className="text-paragraph-sm-medium text-green-600 animate-in fade-in duration-300">
            {t('checkEmail.resent')}
          </p>
        )}
        {limited && (
          <p
            role="alert"
            className="text-paragraph-sm-medium text-destructive animate-in fade-in duration-300"
          >
            {limited}
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
        <InlineLink href={ROUTES.auth.login}>{t('checkEmail.backToLogin')}</InlineLink>
      </div>
    </AuthStatusScreen>
  );
}
