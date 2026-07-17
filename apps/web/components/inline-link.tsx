import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

// Text color per variant (applied to the root).
const INLINE_LINK_TEXT = {
  blue: 'text-blue-700',
  brand: 'text-blue-800',
  muted: 'text-muted-foreground hover:text-foreground',
} as const;

// Hover underline color. decoration starts transparent and transitions in. Two forms because the
// no-icon layout underlines the root itself (self `hover:`) while the icon layout underlines a
// descendant span, which must react to hovering the whole link — i.e. the root `group` (`group-hover`,
// a descendant selector that would never match on the root itself).
const INLINE_LINK_UNDERLINE_SELF = {
  blue: 'hover:decoration-blue-700',
  brand: 'hover:decoration-blue-800',
  muted: 'hover:decoration-foreground',
} as const;
const INLINE_LINK_UNDERLINE_GROUP = {
  blue: 'group-hover/inline-link:decoration-blue-700',
  brand: 'group-hover/inline-link:decoration-blue-800',
  muted: 'group-hover/inline-link:decoration-foreground',
} as const;

// Default type scale per size. Callers can override the size/weight via className (twMerge wins).
const INLINE_LINK_SIZES = {
  sm: 'text-paragraph-sm-medium',
  md: 'text-heading-5',
} as const;

// The animated underline shared by both layouts.
const UNDERLINE =
  'underline decoration-transparent underline-offset-2 transition-colors duration-200 ease-out';

interface InlineLinkBaseProps {
  color?: keyof typeof INLINE_LINK_TEXT;
  size?: keyof typeof INLINE_LINK_SIZES;
  // Optional leading icon (rotates on hover, like the nav items); the underline stays under the text only.
  icon?: LucideIcon;
  className?: string;
  children: React.ReactNode;
}

// Either a navigation (href, optionally a download) or an in-page action (onClick) — same affordance.
type InlineLinkProps = InlineLinkBaseProps &
  (
    | { href: string; download?: boolean; external?: boolean; onClick?: never }
    | { onClick: () => void; href?: never; download?: never; external?: never }
  );

/*
 * Shared inline text link/action used across the auth surface, the public footer/legal links, the
 * brand wordmark, and inline actions (e.g. replaying the welcome tour). Hover reveals an animated
 * underline (text-decoration-color transitions in/out); an optional leading icon rotates on hover.
 * Keyboard focus replaces the default browser outline with the gentlest spring "bump"
 * (animate-focus-bump-subtle — a true 1→1.05→1 keyframe, sized for text where the 1.15 soft bump
 * moves too much), so focus reads distinct from hover. Renders a `<Link>` when given an `href`
 * (or a plain `<a target="_blank" rel="noopener noreferrer">` when `external` — Next `<Link>` is for
 * internal routes), otherwise a `<button>` for the action — the styling is identical.
 */
export function InlineLink(props: InlineLinkProps) {
  const { color = 'blue', size = 'sm', icon: Icon, className, children } = props;
  const root = cn(
    'group/inline-link outline-none transition-colors duration-200 ease-out focus-visible:animate-focus-bump-subtle',
    // With an icon the root is a flex row (underline lives on the text span); without, the root is
    // the inline underlined text itself so it flows in running copy.
    Icon
      ? 'inline-flex items-center gap-x-1.5'
      : cn('inline-block', UNDERLINE, INLINE_LINK_UNDERLINE_SELF[color]),
    INLINE_LINK_SIZES[size],
    INLINE_LINK_TEXT[color],
    className,
  );

  const content = Icon ? (
    <>
      <Icon className="size-4 shrink-0 transition-transform duration-200 ease-out group-hover/inline-link:rotate-12 group-focus-visible/inline-link:rotate-12" />
      <span className={cn(UNDERLINE, INLINE_LINK_UNDERLINE_GROUP[color])}>{children}</span>
    </>
  ) : (
    children
  );

  if ('href' in props && props.href !== undefined && props.external) {
    return (
      <a href={props.href} target="_blank" rel="noopener noreferrer" className={root}>
        {content}
      </a>
    );
  }

  // In-page anchor: a bare hash is same-page navigation, so render a plain <a>, not a Next <Link>
  // (Next intercepts the click). Smooth scroll comes from an ancestor's useSmoothScrollToHash
  // delegation; without one the link still works, degrading to a native jump.
  if ('href' in props && props.href !== undefined && props.href.startsWith('#')) {
    return (
      <a href={props.href} className={root}>
        {content}
      </a>
    );
  }

  if ('href' in props && props.href !== undefined) {
    return (
      <Link
        href={props.href}
        download={props.download}
        prefetch={props.download ? false : undefined}
        className={root}
      >
        {content}
      </Link>
    );
  }

  return (
    <button type="button" onClick={props.onClick} className={root}>
      {content}
    </button>
  );
}
