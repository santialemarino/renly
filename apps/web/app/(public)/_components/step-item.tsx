'use client';

import { RevealItem } from '@/app/(public)/_components/reveal';

interface StepItemProps {
  index: number;
  title: string;
  description: string;
}

// A single numbered "How it works" step. Reveals in sequence via its RevealGroup parent; the number
// circle nudges up in scale on hover (motion-safe-gated) for a subtle touch.
export function StepItem({ index, title, description }: StepItemProps) {
  return (
    <RevealItem as="li" className="group flex items-start gap-x-4">
      <span className="flex size-8 shrink-0 items-center justify-center bg-blue-800 rounded-full transition-transform duration-200 ease-out motion-safe:group-hover:scale-110 text-paragraph-sm-semibold text-white">
        {index + 1}
      </span>
      <div className="flex flex-col gap-y-1">
        <h3 className="text-heading-5 text-neutral-950">{title}</h3>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
      </div>
    </RevealItem>
  );
}
