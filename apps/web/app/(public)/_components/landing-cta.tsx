import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';

// Closing call-to-action that nudges the visitor to create an account.
export async function LandingCta() {
  const t = await getTranslations('landing.cta');

  return (
    <section className="flex flex-col w-full max-w-2xl items-center self-center px-6 pt-16 pb-24 gap-y-5 text-center">
      <h2 className="text-heading-2 text-neutral-950">{t('title')}</h2>
      <p className="text-paragraph text-muted-foreground">{t('subtitle')}</p>
      <Button asChild blue size="lg">
        <a href={ROUTES.auth.signup}>{t('button')}</a>
      </Button>
    </section>
  );
}
