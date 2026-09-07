'use client';

import { useTranslations } from 'next-intl';

import { DismissableHint } from '@/components/dismissable-hint';
import { InlineLink } from '@/components/inline-link';
import { helpAnchorPath, type HelpAnchor } from '@/config/routes';

interface ConceptHintProps {
  storageKey: string;
  // The help section this concept is explained in full on.
  anchor: HelpAnchor;
  show?: boolean;
  // The hint's copy — deliberately owned by the caller, so each page words its own nudge.
  children: React.ReactNode;
}

/*
 * A dismissable hint that teaches one concept and links to the help section explaining it in full.
 * The composite (hint + copy + a trailing "Learn more" link) is what every page-level concept nudge
 * renders, so it lives here rather than being reassembled per page — the shared parts are the
 * affordance and the "Learn more" label, never the copy.
 *
 * A CLIENT component, so the same composite serves both surfaces: the four page-level nudges render it
 * from a server page (which a client component is perfectly happy to be), and the group hub's
 * co-ownership nudge renders it from inside a client section. It wraps `DismissableHint`, which reads
 * localStorage and is therefore client-only anyway, so the boundary sits one level up and nothing is
 * lost. The alternative was a second component or a slot prop per client caller, either of which puts
 * the composite back in the callers' hands — the exact reassembly this component exists to prevent.
 */
export function ConceptHint({ storageKey, anchor, show, children }: ConceptHintProps) {
  const tCommon = useTranslations('common');

  return (
    <DismissableHint storageKey={storageKey} show={show}>
      {children}{' '}
      <InlineLink href={helpAnchorPath(anchor)} color="brand">
        {tCommon('learnMore')}
      </InlineLink>
    </DismissableHint>
  );
}
