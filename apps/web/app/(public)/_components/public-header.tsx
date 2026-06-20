import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';

// Top bar shared by the landing and legal pages: brand wordmark + log in / sign up.
export async function PublicHeader() {
  const t = await getTranslations('common.publicHeader');
  const tCommon = await getTranslations('common');

  return (
    <header className="sticky top-0 z-40 flex w-full items-center justify-between px-6 py-4 border-b border-neutral-200 bg-background/80 backdrop-blur">
      <a href={ROUTES.landing} className="text-heading-5 text-blue-800">
        {tCommon('appName')}
      </a>
      <nav className="flex items-center gap-x-2">
        <Button asChild variant="ghost" size="sm">
          <a href={ROUTES.auth.login}>{t('login')}</a>
        </Button>
        <Button asChild blue size="sm">
          <a href={ROUTES.auth.signup}>{t('signup')}</a>
        </Button>
      </nav>
    </header>
  );
}
