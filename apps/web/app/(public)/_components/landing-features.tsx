'use client';

import { Blocks, Globe, LineChart, ShieldCheck, Wallet, Zap, type LucideIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { FeatureCard } from '@/app/(public)/_components/feature-card';
import { Reveal, RevealGroup } from '@/app/(public)/_components/reveal';
import { Section } from '@/app/(public)/_components/section';

interface FeatureItem {
  // Names the card's icon in FEATURE_ICONS. Keyed rather than positional so reordering or
  // translating the list carries each item's icon with it.
  icon: string;
  title: string;
  description: string;
}

export const FEATURE_ICONS: Record<string, LucideIcon> = {
  blocks: Blocks,
  globe: Globe,
  'line-chart': LineChart,
  'shield-check': ShieldCheck,
  wallet: Wallet,
  zap: Zap,
};

// "Why Renly" — the six core product values rendered as a responsive grid of icon cards.
export function LandingFeatures() {
  const t = useTranslations('landing.features');
  const items = t.raw('items') as FeatureItem[];

  return (
    <Section width="wide" className="py-16 gap-y-10">
      <Reveal>
        <h2 className="text-heading-2 text-neutral-950 text-center">{t('title')}</h2>
      </Reveal>
      <RevealGroup className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <FeatureCard
            key={item.title}
            icon={FEATURE_ICONS[item.icon] ?? Zap}
            title={item.title}
            description={item.description}
          />
        ))}
      </RevealGroup>
    </Section>
  );
}
