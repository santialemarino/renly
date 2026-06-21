'use client';

import type { LucideIcon } from 'lucide-react';

import { Card } from '@repo/ui/components';
import { RevealItem } from '@/app/(public)/_components/reveal';

interface FeatureCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

/*
 * A single "Why Renly" value card. The RevealItem owns the hover region and stays put — the inner
 * Card is the layer that lifts, so the pointer never falls outside the hovered element at the
 * boundary (the hover-lift flicker fix). The icon rotates on hover like the sidebar nav icons.
 * Both the lift and the rotate are motion-safe-gated so reduced motion shows neither.
 *
 * The transition lists `translate` (not `transform`): in Tailwind v4 `-translate-y-*` sets the
 * individual `translate` CSS property, so transitioning `transform` would leave the lift instant.
 */
export function FeatureCard({ icon: Icon, title, description }: FeatureCardProps) {
  return (
    <RevealItem className="group h-full">
      <Card
        compact
        className="h-full p-6 gap-y-3 transition-[translate,box-shadow] duration-200 ease-out group-hover:shadow-lg motion-safe:group-hover:-translate-y-1.5"
      >
        <Icon className="size-6 transition-transform duration-200 ease-out motion-safe:group-hover:rotate-12 text-blue-800" />
        <h3 className="text-heading-5 text-neutral-950">{title}</h3>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
      </Card>
    </RevealItem>
  );
}
