'use client';

import { useSmoothScrollToHash } from '@/app/(public)/_components/use-smooth-scroll-to-hash';
import { InlineLink } from '@/components/inline-link';

interface HelpTocProps {
  label: string;
  sections: { id: string; heading: string }[];
}

// The help page's "on this page" table of contents. Client-side so a delegated handler can smoothly
// scroll to each section (reduced-motion aware) rather than jumping.
export function HelpToc({ label, sections }: HelpTocProps) {
  const scrollToHash = useSmoothScrollToHash();

  return (
    <nav
      aria-labelledby="help-toc-label"
      onClick={scrollToHash}
      className="flex flex-col p-5 gap-y-3 bg-muted/30 border border-neutral-200 rounded-2xl"
    >
      <span id="help-toc-label" className="text-paragraph-sm-semibold text-neutral-950">
        {label}
      </span>
      <ul className="flex flex-col gap-y-1.5">
        {sections.map((section) => (
          <li key={section.id}>
            <InlineLink href={`#${section.id}`}>{section.heading}</InlineLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
