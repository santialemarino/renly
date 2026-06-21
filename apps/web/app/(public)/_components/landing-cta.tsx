'use client';

import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { RevealGroup, RevealItem } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';
import { ROUTES } from '@/config/routes';

// Closing call-to-action that nudges the visitor to create an account; staggers in on scroll.
export function LandingCta() {
  const t = useTranslations('landing.cta');

  return (
    <Section width="narrow" className="pt-16 pb-24">
      <RevealGroup className="flex flex-col items-center gap-y-5 text-center">
        <RevealItem>
          <h2 className="text-heading-2 text-neutral-950">{t('title')}</h2>
        </RevealItem>
        <RevealItem>
          <p className="text-paragraph text-muted-foreground">{t('subtitle')}</p>
        </RevealItem>
        <RevealItem>
          <Button asChild blue size="lg">
            <a href={ROUTES.auth.signup}>{t('button')}</a>
          </Button>
        </RevealItem>
      </RevealGroup>
    </Section>
  );
}
