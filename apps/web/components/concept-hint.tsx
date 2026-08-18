import { getTranslations } from 'next-intl/server';

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
 */
export async function ConceptHint({ storageKey, anchor, show, children }: ConceptHintProps) {
  const tCommon = await getTranslations('common');

  return (
    <DismissableHint storageKey={storageKey} show={show}>
      {children}{' '}
      <InlineLink href={helpAnchorPath(anchor)} color="brand">
        {tCommon('learnMore')}
      </InlineLink>
    </DismissableHint>
  );
}
