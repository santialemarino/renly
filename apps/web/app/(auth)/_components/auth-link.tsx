import Link from 'next/link';

import { cn } from '@repo/ui/lib';

interface AuthLinkProps {
  href: string;
  className?: string;
  children: React.ReactNode;
}

// Shared auth link, consistent across the whole auth surface. Hover reveals an animated underline
// (text-decoration-color transitions in/out). Keyboard focus replaces the default browser outline
// with the app's soft spring "bump" (animate-focus-bump-soft — a true 1→1.15→1 keyframe, the same
// one inline links use in link-card / integrations-shortcut), so focus reads distinct from hover.
// inline-block lets the scale transform apply to the inline link without a layout shift.
export function AuthLink({ href, className, children }: AuthLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        'inline-block text-paragraph-sm-medium text-blue-700 underline decoration-transparent underline-offset-2 outline-none transition-colors duration-200 ease-out hover:decoration-blue-700 focus-visible:animate-focus-bump-soft',
        className,
      )}
    >
      {children}
    </Link>
  );
}
