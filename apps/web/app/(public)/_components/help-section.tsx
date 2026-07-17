'use client';

import { Reveal } from '@/app/(public)/_components/reveal';

interface HelpSectionProps {
  id: string;
  heading: string;
  paragraphs?: string[];
  items?: string[];
}

/*
 * One topic block of the help page: an anchored heading plus paragraphs/bullets, gently revealed as
 * it scrolls into view. The `id` lives on the heading so table-of-contents and in-app deep links
 * (e.g. /help#returns) land on it; `scroll-mt` offsets the sticky public header so the heading isn't
 * hidden underneath after the jump.
 */
export function HelpSection({ id, heading, paragraphs, items }: HelpSectionProps) {
  return (
    <Reveal as="section" className="flex flex-col gap-y-3">
      <h2 id={id} className="scroll-mt-24 text-heading-4 text-neutral-950">
        {heading}
      </h2>
      {paragraphs?.map((paragraph, index) => (
        <p key={index} className="text-paragraph-sm text-muted-foreground">
          {paragraph}
        </p>
      ))}
      {items && (
        <ul className="flex flex-col pl-5 gap-y-1 list-disc">
          {items.map((item, index) => (
            <li key={index} className="text-paragraph-sm text-muted-foreground">
              {item}
            </li>
          ))}
        </ul>
      )}
    </Reveal>
  );
}
