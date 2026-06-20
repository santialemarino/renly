import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';

// Above-the-fold marketing hero: headline, sub-headline, and the primary signup / login CTAs.
export async function LandingHero() {
  const t = await getTranslations('landing.hero');

  return (
    <section className="flex flex-col w-full max-w-3xl items-center self-center px-6 pt-20 pb-16 gap-y-6 text-center">
      <h1 className="text-heading-1 text-neutral-950">{t('title')}</h1>
      <p className="max-w-2xl text-paragraph text-muted-foreground">{t('subtitle')}</p>
      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-3">
        <Button asChild blue size="lg">
          <a href={ROUTES.auth.signup}>{t('ctaPrimary')}</a>
        </Button>
        <Button asChild variant="outline" size="lg">
          <a href={ROUTES.auth.login}>{t('ctaSecondary')}</a>
        </Button>
      </div>
    </section>
  );
}
