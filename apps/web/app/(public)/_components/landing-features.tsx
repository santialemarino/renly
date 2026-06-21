'use client';

import { Blocks, Globe, LineChart, ShieldCheck, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { FeatureCard } from '@/app/(public)/_components/feature-card';
import { Reveal, RevealGroup } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';

interface FeatureItem {
  title: string;
  description: string;
}

// Icons pair with the translated feature list by position (fast entry, clarity, trust, context, growth).
const FEATURE_ICONS = [Zap, LineChart, ShieldCheck, Globe, Blocks];

// "Why Renly" — the five core product values rendered as a responsive grid of icon cards.
export function LandingFeatures() {
  const t = useTranslations('landing.features');
  const items = t.raw('items') as FeatureItem[];

  return (
    <Section width="wide" className="py-16 gap-y-10">
      <Reveal>
        <h2 className="text-heading-2 text-neutral-950 text-center">{t('title')}</h2>
      </Reveal>
      <RevealGroup className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {items.map((item, index) => (
          <FeatureCard
            key={item.title}
            icon={FEATURE_ICONS[index] ?? Zap}
            title={item.title}
            description={item.description}
          />
        ))}
      </RevealGroup>
    </Section>
  );
}
