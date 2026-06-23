import { cn } from '@repo/ui/lib';

interface SectionHeaderProps {
  title: string;
  description: string;
  // 'destructive' tints the title (danger zone); 'default' uses the muted preferences-style heading.
  variant?: 'default' | 'destructive';
}

// Title + description block shared by the account page sections (matches the preferences layout).
export function SectionHeader({ title, description, variant = 'default' }: SectionHeaderProps) {
  return (
    <div className="flex flex-col gap-y-1">
      <h3
        className={cn(
          'text-paragraph-sm-semibold',
          variant === 'destructive' ? 'text-destructive' : 'text-muted-foreground',
        )}
      >
        {title}
      </h3>
      <p className="text-paragraph-xs text-muted-foreground">{description}</p>
    </div>
  );
}
