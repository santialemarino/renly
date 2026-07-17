import { cn } from '@repo/ui/lib';
import { Reveal } from '@/app/(public)/_components/reveal';

export interface ProseSectionData {
  // When set, the heading becomes an anchor target (table of contents / deep links).
  id?: string;
  heading: string;
  paragraphs?: string[];
  items?: string[];
}

/*
 * One prose block of a content page (the legal pages and the help page): a heading plus
 * paragraphs/bullets, gently revealed as it scrolls into view. When `id` is set the heading is an
 * anchor target and gets `scroll-mt-*` so it lands clear of the sticky public header after a jump.
 */
export function ProseSection({ id, heading, paragraphs, items }: ProseSectionData) {
  return (
    <Reveal as="section" className="flex flex-col gap-y-3">
      <h2 id={id} className={cn('text-heading-4 text-neutral-950', id && 'scroll-mt-24')}>
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
