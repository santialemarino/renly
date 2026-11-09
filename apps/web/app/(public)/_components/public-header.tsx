import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { Brand } from '@/components/brand';
import { ROUTES } from '@/config/routes';
import { getSignupContext } from '@/lib/api/signup-context';
import { getSession, isAuthenticatedSession } from '@/lib/auth';

// Top bar shared by the landing, help, and legal pages: brand wordmark + auth CTAs. Logged-out
// visitors get sign up / log in; logged-in visitors get a single "go to the app" CTA instead. While
// signup is invite-only there is no sign up to offer, so "Log in" is the one CTA (the landing explains
// invites; this bar is on every public page and stays short).
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
      {/* Named, like every nav landmark: the footer has one too, and two unnamed ones read alike. */}
      <nav aria-label={t('navLabel')} className="flex items-center gap-x-2">
        {isAuthenticated ? (
          <Button asChild blue size="sm">
            <a href={ROUTES.home}>{tCommon('goToDashboard')}</a>
          </Button>
        ) : mode === 'invite' ? (
          // The same outline button as in open mode, only alone: the landing's own CTAs are the
          // primary ones, and this bar's focus ring is the one the focus-system spec measures.
          <Button asChild variant="outline" size="sm">
            <a href={ROUTES.auth.login}>{t('login')}</a>
          </Button>
        ) : (
          <>
            <Button asChild blue size="sm">
              <a href={ROUTES.auth.signup}>{t('signup')}</a>
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
