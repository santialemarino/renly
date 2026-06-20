import Link from 'next/link';

import { cn } from '@repo/ui/lib';

interface AuthLinkProps {
  href: string;
  className?: string;
  children: React.ReactNode;
}

// Shared auth link, consistent across the whole auth surface. Hover reveals an animated underline
// (text-decoration-color transitions in/out). Keyboard focus replaces the default browser outline
// with the small scale "bump" used elsewhere in the app (search-input / currency-combobox), so
// focus reads distinct from hover. inline-block lets the transform apply without layout shift.
export function AuthLink({ href, className, children }: AuthLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        'inline-block text-paragraph-sm-medium text-blue-700 underline decoration-transparent underline-offset-2 outline-none transition-all duration-200 ease-out hover:decoration-blue-700 focus-visible:scale-105',
        className,
      )}
    >
      {children}
    </Link>
  );
}
