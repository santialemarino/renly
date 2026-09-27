'use client';

import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { MAIN_CONTENT_ID } from '@/config/constants';

/*
 * "Skip to main content" — the first focusable element of every layout that puts a block of
 * navigation before its `<main>` (WCAG 2.4.1). Without it a keyboard reader crossed the whole sidebar
 * on every page: seventeen tab stops before the first control of a list.
 *
 * Visually hidden until focused (`not-focus:sr-only`, so no motion and nothing to animate), then a
 * plain outline button pinned to the corner above the sticky header, with the Button's own focus ring.
 * A real `href` so it still works as a link, but the click moves focus itself: the browser's fragment
 * navigation would also push `#main-content` into the history, making Back step through a hash.
 * The target `<main>` carries `tabIndex={-1}`, so focus can land on it and the next Tab continues from
 * the top of the page's own content.
 */
export function SkipLink() {
  const t = useTranslations('common');

  function handleClick(event: React.MouseEvent<HTMLAnchorElement>) {
    const main = document.getElementById(MAIN_CONTENT_ID);
    if (!main) return;
    event.preventDefault();
    main.focus();
  }

  return (
    <Button
      asChild
      variant="outline"
      className="fixed top-3 left-3 z-50 not-focus:sr-only"
      data-testid="skip-link"
    >
      <a href={`#${MAIN_CONTENT_ID}`} onClick={handleClick}>
        {t('skipToContent')}
      </a>
    </Button>
  );
}
