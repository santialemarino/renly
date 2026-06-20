import { Blocks, Globe, LineChart, ShieldCheck, Zap } from 'lucide-react';
import { getTranslations } from 'next-intl/server';

import { Card } from '@repo/ui/components';

interface FeatureItem {
  title: string;
  description: string;
}

// Icons pair with the translated feature list by position (fast entry, clarity, trust, context, growth).
const FEATURE_ICONS = [Zap, LineChart, ShieldCheck, Globe, Blocks];

// "Why Renly" — the five core product values rendered as a responsive grid of icon cards.
export async function LandingFeatures() {
  const t = await getTranslations('landing.features');
  const items = t.raw('items') as FeatureItem[];

  return (
    <section className="flex flex-col w-full max-w-5xl items-center self-center px-6 py-16 gap-y-10">
      <h2 className="text-heading-2 text-neutral-950 text-center">{t('title')}</h2>
      <div className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {items.map((item, index) => {
          const Icon = FEATURE_ICONS[index] ?? Zap;
          return (
            <Card key={item.title} compact className="gap-y-3 p-6">
              <Icon className="size-6 text-blue-800" />
              <h3 className="text-heading-5 text-neutral-950">{item.title}</h3>
              <p className="text-paragraph-sm text-muted-foreground">{item.description}</p>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
