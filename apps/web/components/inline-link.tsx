import Link from 'next/link';

import { cn } from '@repo/ui/lib';

// Text color + the matching hover underline color. decoration starts transparent and transitions in.
const INLINE_LINK_COLORS = {
  blue: 'text-blue-700 hover:decoration-blue-700',
  brand: 'text-blue-800 hover:decoration-blue-800',
  muted: 'text-muted-foreground hover:text-foreground hover:decoration-foreground',
} as const;

// Default type scale per size. Callers can override the size/weight via className (twMerge wins).
const INLINE_LINK_SIZES = {
  sm: 'text-paragraph-sm-medium',
  md: 'text-heading-5',
} as const;

interface InlineLinkProps {
  href: string;
  color?: keyof typeof INLINE_LINK_COLORS;
  size?: keyof typeof INLINE_LINK_SIZES;
  className?: string;
  children: React.ReactNode;
}

/*
 * Shared inline text link used across the auth surface, the public footer/legal links, and the
 * brand wordmark. Hover reveals an animated underline (text-decoration-color transitions in/out).
 * Keyboard focus replaces the default browser outline with the gentlest spring "bump"
 * (animate-focus-bump-subtle — a true 1→1.05→1 keyframe, sized for text where the 1.15 soft bump
 * moves too much), so focus reads distinct from hover. inline-block lets the scale transform apply
 * to the inline link without a layout shift.
 */
export function InlineLink({
  href,
  color = 'blue',
  size = 'sm',
  className,
  children,
}: InlineLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        'inline-block underline decoration-transparent underline-offset-2 outline-none transition-colors duration-200 ease-out focus-visible:animate-focus-bump-subtle',
        INLINE_LINK_SIZES[size],
        INLINE_LINK_COLORS[color],
        className,
      )}
    >
      {children}
    </Link>
  );
}
