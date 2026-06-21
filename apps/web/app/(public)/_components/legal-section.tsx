'use client';

import { Reveal } from '@/app/(public)/_components/reveal';

interface LegalSectionProps {
  heading: string;
  paragraphs?: string[];
  items?: string[];
}

// One heading + paragraphs/bullets block of a legal page; gently reveals as it scrolls into view.
export function LegalSection({ heading, paragraphs, items }: LegalSectionProps) {
  return (
    <Reveal as="section" className="flex flex-col gap-y-3">
      <h2 className="text-heading-4 text-neutral-950">{heading}</h2>
      {paragraphs?.map((paragraph) => (
        <p key={paragraph.slice(0, 32)} className="text-paragraph-sm text-muted-foreground">
          {paragraph}
        </p>
      ))}
      {items && (
        <ul className="flex flex-col pl-5 gap-y-1 list-disc">
          {items.map((item) => (
            <li key={item.slice(0, 32)} className="text-paragraph-sm text-muted-foreground">
              {item}
            </li>
          ))}
        </ul>
      )}
    </Reveal>
  );
}
