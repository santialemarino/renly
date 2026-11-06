import { ANIMATION_DEFAULT, PAGE_SKELETON_DELAY_MS } from '@/lib/constants/animations';

interface ProtectedTemplateProps {
  children: React.ReactNode;
}

/*
 * Every protected page's entrance. Next mounts a template afresh on each navigation and renders the
 * route's loading state inside it, so this one box carries both halves of the rule (the CSS is the
 * `.page-entrance` block in `globals.css`):
 *
 * - the page fades in once, as a whole, when it mounts or when its loading state gives way to it;
 * - the loading state is invisible for `PAGE_SKELETON_DELAY_MS` and only then fades in, so a fast
 *   load shows nothing in between and a slow one shows the skeleton rather than a frozen screen.
 *
 * The timings are set here, from the shared constants, as the two CSS variables the rules read. The
 * box is a flex column like the `<main>` around it, so the pages lay out as they did without it.
 */
export default function ProtectedTemplate({ children }: ProtectedTemplateProps) {
  return (
    <div
      className="page-entrance flex flex-col flex-1 min-w-0"
      style={
        {
          '--page-entrance-duration': `${ANIMATION_DEFAULT}s`,
          '--page-skeleton-delay': `${PAGE_SKELETON_DELAY_MS}ms`,
        } as React.CSSProperties
      }
    >
      {children}
    </div>
  );
}
