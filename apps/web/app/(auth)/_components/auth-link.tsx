import Link from 'next/link';

import { cn } from '@repo/ui/lib';

interface AuthLinkProps {
  href: string;
  className?: string;
  children: React.ReactNode;
}

// Shared auth link with an underline that animates in/out on hover (text-decoration-color
// transitions via transition-colors), keeping every auth-surface link visually consistent.
export function AuthLink({ href, className, children }: AuthLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        'text-paragraph-sm-medium text-blue-700 underline decoration-transparent underline-offset-2 transition-colors duration-200 ease-out hover:decoration-blue-700',
        className,
      )}
    >
      {children}
    </Link>
  );
}
