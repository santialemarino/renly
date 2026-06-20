import { type LucideIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

type Tone = 'info' | 'success' | 'error';

// Icon + halo colors per tone, so every auth result screen shares one visual language.
const TONE_STYLES: Record<Tone, { icon: string; halo: string }> = {
  info: { icon: 'text-blue-600', halo: 'bg-blue-50' },
  success: { icon: 'text-green-500', halo: 'bg-green-50' },
  error: { icon: 'text-destructive', halo: 'bg-destructive/10' },
};

interface AuthStatusScreenProps {
  icon: LucideIcon;
  tone: Tone;
  title: string;
  description: string;
  children?: React.ReactNode;
}

// Shared result screen for the auth flows (check-email, reset done, verification result, etc.):
// a haloed, zoom-in icon over a title + description, with optional actions below. Centralizing it
// keeps the icon treatment, spacing, and animation identical across every screen.
export function AuthStatusScreen({
  icon: Icon,
  tone,
  title,
  description,
  children,
}: AuthStatusScreenProps) {
  const styles = TONE_STYLES[tone];

  return (
    <div className="flex flex-col items-center px-6 gap-y-6 text-center">
      <div className="relative flex items-center justify-center">
        <div className={cn('absolute size-24 rounded-full', styles.halo)} />
        <Icon className={cn('relative size-16 animate-in zoom-in-50 duration-500', styles.icon)} />
      </div>

      <div className="flex flex-col gap-y-2">
        <p className="text-paragraph-semibold text-foreground">{title}</p>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
      </div>

      {children}
    </div>
  );
}
