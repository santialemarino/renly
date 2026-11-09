import { getTranslations } from 'next-intl/server';

import { Button } from '@repo/ui/components';
import { InviteHelp } from '@/app/(public)/_components/invite-help';
import { RevealGroup, RevealItem } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';
import { ROUTES } from '@/config/routes';
import type { SignupMode } from '@/lib/auth-api';

interface LandingCtaProps {
  signupMode: SignupMode;
}

// Closing call-to-action that nudges the visitor to create an account; staggers in on scroll. While
// signup is invite-only it offers what the hero does instead — "Log in" and "Have an invite?" — with
// copy that does not promise an account anyone can create.
export async function LandingCta({ signupMode }: LandingCtaProps) {
  const t = await getTranslations('landing.cta');
  const tHero = await getTranslations('landing.hero');
  const inviteOnly = signupMode === 'invite';

  return (
    <Section width="narrow" className="pt-16 pb-24">
      <RevealGroup className="flex flex-col items-center gap-y-5 text-center">
        <RevealItem>
          <h2 className="text-heading-2 text-neutral-950">{t('title')}</h2>
        </RevealItem>
        <RevealItem>
          <p className="text-paragraph text-muted-foreground">
            {inviteOnly ? t('inviteSubtitle') : t('subtitle')}
          </p>
        </RevealItem>
        {inviteOnly ? (
          <RevealItem className="flex flex-wrap items-center justify-center gap-x-3 gap-y-3">
            <Button asChild blue size="lg">
              <a href={ROUTES.auth.login}>{tHero('ctaSecondary')}</a>
            </Button>
            <InviteHelp size="lg" />
          </RevealItem>
        ) : (
          <RevealItem>
            <Button asChild blue size="lg">
              <a href={ROUTES.auth.signup}>{t('button')}</a>
            </Button>
          </RevealItem>
        )}
      </RevealGroup>
    </Section>
  );
}
