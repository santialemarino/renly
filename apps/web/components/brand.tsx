import { cn } from '@repo/ui/lib';
import { InlineLink } from '@/components/inline-link';

// Type scale per placement: footer (sm), public header (md), sidebar (lg).
const BRAND_SIZES = {
  sm: 'text-paragraph-semibold',
  md: 'text-heading-5',
  lg: 'text-heading-2',
} as const;

interface BrandProps {
  name: string;
  // Renders as a home link with the shared inline-link treatment when set (public header);
  // plain text otherwise (sidebar, footer).
  href?: string;
  size?: keyof typeof BRAND_SIZES;
  className?: string;
}

// Renly wordmark — the blue-800 brand text, shared across the sidebar, public header, and footer.
export function Brand({ name, href, size = 'md', className }: BrandProps) {
  if (href) {
    return (
      <InlineLink href={href} color="brand" className={cn(BRAND_SIZES[size], className)}>
        {name}
      </InlineLink>
    );
  }

  return <span className={cn('text-blue-800', BRAND_SIZES[size], className)}>{name}</span>;
}
