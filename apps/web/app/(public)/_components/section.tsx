import { cn } from '@repo/ui/lib';

// Max content width per section; the column is centered with uniform horizontal padding.
const SECTION_WIDTHS = {
  narrow: 'max-w-2xl',
  default: 'max-w-3xl',
  wide: 'max-w-5xl',
} as const;

interface SectionProps {
  width?: keyof typeof SECTION_WIDTHS;
  className?: string;
  children: React.ReactNode;
}

// Shared layout shell for the public landing sections: a centered column with a capped width and
// uniform horizontal padding. Vertical padding and gap come from className so each section tunes its own.
export function Section({ width = 'default', className, children }: SectionProps) {
  return (
    <section
      className={cn(
        'flex flex-col w-full',
        SECTION_WIDTHS[width],
        'items-center self-center px-6',
        className,
      )}
    >
      {children}
    </section>
  );
}
