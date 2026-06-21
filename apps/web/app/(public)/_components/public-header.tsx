import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { Brand } from '@/components/brand';
import { ROUTES } from '@/config/routes';

// Top bar shared by the landing and legal pages: brand wordmark + sign up / log in.
// The before: layer extends the header color into the overscroll-bounce area above it, so the
// sticky/translucent header shows no seam at the very top when the page rubber-bands.
export async function PublicHeader() {
  const t = await getTranslations('common.publicHeader');
  const tCommon = await getTranslations('common');

  return (
    <header className="sticky top-0 z-40 flex w-full items-center justify-between px-6 py-4 border-b border-neutral-200 bg-background/80 backdrop-blur before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-screen before:bg-background before:content-['']">
      <Brand name={tCommon('appName')} href={ROUTES.landing} size="md" />
      <nav className="flex items-center gap-x-2">
        <Button asChild blue size="sm">
          <a href={ROUTES.auth.signup}>{t('signup')}</a>
        </Button>
        <Button asChild variant="outline" size="sm">
          <a href={ROUTES.auth.login}>{t('login')}</a>
        </Button>
      </nav>
    </header>
  );
}
