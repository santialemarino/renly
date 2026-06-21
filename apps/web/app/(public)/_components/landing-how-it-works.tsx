'use client';

import { useTranslations } from 'next-intl';

import { Reveal, RevealGroup } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';
import { StepItem } from '@/app/(public)/_components/step-item';

interface HowItWorksStep {
  title: string;
  description: string;
}

// "How it works" — the numbered onboarding steps, set inside a rounded, tinted inset panel.
export function LandingHowItWorks() {
  const t = useTranslations('landing.howItWorks');
  const steps = t.raw('steps') as HowItWorksStep[];

  return (
    <Section width="default" className="py-16">
      <div className="flex flex-col w-full items-center p-8 gap-y-10 bg-muted/30 rounded-2xl sm:p-10">
        <Reveal>
          <h2 className="text-heading-2 text-neutral-950 text-center">{t('title')}</h2>
        </Reveal>
        <RevealGroup as="ol" className="flex flex-col w-full gap-y-6">
          {steps.map((step, index) => (
            <StepItem
              key={step.title}
              index={index}
              title={step.title}
              description={step.description}
            />
          ))}
        </RevealGroup>
      </div>
    </Section>
  );
}
