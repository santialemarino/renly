import { Lock } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { Card } from '@repo/ui/components';
import { AuthStatusScreen } from '@/app/(auth)/_components/auth-status-screen';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';

// Shown at /signup in invite-only mode without a valid invite link: explains that Renly is
// invite-only and routes existing users to log in. Deliberately renders NO registration form — an
// uninvited visitor can't submit an email, so nothing about account existence leaks (anti-enumeration).
export async function InviteOnlyNotice() {
  const t = await getTranslations('signup.inviteOnly');

  return (
    <div className="w-full max-w-auth-form">
      <Card>
        <AuthStatusScreen icon={Lock} tone="info" title={t('title')} description={t('description')}>
          <div className="flex items-center px-6 gap-x-1 text-paragraph-sm text-muted-foreground">
            <span>{t('haveAccount')}</span>
            <InlineLink href={ROUTES.auth.login}>{t('login')}</InlineLink>
          </div>
        </AuthStatusScreen>
      </Card>
    </div>
  );
}
