import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { Brand } from '@/components/brand';
import { ROUTES } from '@/config/routes';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession, isAuthenticatedSession } from '@/lib/auth';

// Top bar shared by the landing and legal pages: brand wordmark + auth CTAs. Logged-out visitors
// get sign up / log in; logged-in visitors get a single "go to the app" CTA instead. In invite-only
// mode the sign-up CTA reads "Request access" (routes to the invite-only signup screen).
// The before: layer extends the header color into the overscroll-bounce area above it, so the
// sticky/translucent header shows no seam at the very top when the page rubber-bands.
export async function PublicHeader() {
  const t = await getTranslations('common.publicHeader');
  const tCommon = await getTranslations('common');
  const [session, { mode }] = await Promise.all([getSession(), getSignupContext()]);
  const isAuthenticated = isAuthenticatedSession(session);

  return (
    <header className="sticky top-0 z-40 flex w-full items-center justify-between px-6 py-4 border-b border-neutral-200 bg-background/80 backdrop-blur before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-screen before:bg-background before:content-['']">
      <Brand name={tCommon('appName')} href={ROUTES.landing} size="md" />
      <nav className="flex items-center gap-x-2">
        {isAuthenticated ? (
          <Button asChild blue size="sm">
            <a href={ROUTES.home}>{tCommon('goToDashboard')}</a>
          </Button>
        ) : (
          <>
            <Button asChild blue size="sm">
              <a href={ROUTES.auth.signup}>
                {mode === 'invite' ? tCommon('requestAccess') : t('signup')}
              </a>
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={ROUTES.auth.login}>{t('login')}</a>
            </Button>
          </>
        )}
      </nav>
    </header>
  );
}
