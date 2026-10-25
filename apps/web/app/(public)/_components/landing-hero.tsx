import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { RevealGroup, RevealItem } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';
import { ROUTES } from '@/config/routes';
import type { SignupMode } from '@/lib/auth-api';

interface LandingHeroProps {
  isAuthenticated: boolean;
  signupMode: SignupMode;
}

// Above-the-fold marketing hero: headline, sub-headline, and the primary CTAs. Logged-out visitors
// get signup / login; logged-in visitors get a single "go to the app" CTA instead. In invite-only
// mode the primary CTA reads "Request access" (it routes to the invite-only signup screen).
// Entrance staggers in on mount (the public surface's on-load animation).
export async function LandingHero({ isAuthenticated, signupMode }: LandingHeroProps) {
  const t = await getTranslations('landing.hero');
  const tCommon = await getTranslations('common');

  return (
    <Section width="default" className="pt-20 pb-16">
      <RevealGroup onLoad className="flex flex-col items-center gap-y-6 text-center">
        <RevealItem>
          <h1 className="text-heading-1 text-neutral-950">{t('title')}</h1>
        </RevealItem>
        <RevealItem>
          <p className="max-w-2xl text-paragraph text-muted-foreground">{t('subtitle')}</p>
        </RevealItem>
        <RevealItem className="flex flex-wrap items-center justify-center gap-x-3 gap-y-3">
          {isAuthenticated ? (
            <Button asChild blue size="lg">
              <a href={ROUTES.home}>{tCommon('goToDashboard')}</a>
            </Button>
          ) : (
            <>
              <Button asChild blue size="lg">
                <a href={ROUTES.auth.signup}>
                  {signupMode === 'invite' ? tCommon('requestAccess') : t('ctaPrimary')}
                </a>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href={ROUTES.auth.login}>{t('ctaSecondary')}</a>
              </Button>
            </>
          )}
        </RevealItem>
      </RevealGroup>
    </Section>
  );
}
