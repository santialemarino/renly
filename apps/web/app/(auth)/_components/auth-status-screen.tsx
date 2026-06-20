import { type LucideIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';

type Tone = 'info' | 'success' | 'error';

// Icon + circle colors per tone, so every auth result screen shares one visual language.
const TONE_STYLES: Record<Tone, { icon: string; circle: string }> = {
  info: { icon: 'text-blue-600', circle: 'bg-blue-50' },
  success: { icon: 'text-green-500', circle: 'bg-green-50' },
  error: { icon: 'text-destructive', circle: 'bg-destructive/10' },
};

interface AuthStatusScreenProps {
  icon: LucideIcon;
  tone: Tone;
  title: string;
  description: string;
  children?: React.ReactNode;
}

// Shared result screen for the auth flows (check-email, reset done, verification result, etc.):
// a zoom-in icon in a tinted circle over a title + description, with optional actions below.
// The circle is a real (padded) box — not an absolute halo — so its top aligns with where a card
// title sits, and the gap rhythm matches the card's section spacing. Used for every tone.
export function AuthStatusScreen({
  icon: Icon,
  tone,
  title,
  description,
  children,
}: AuthStatusScreenProps) {
  const styles = TONE_STYLES[tone];

  return (
    <div className="flex flex-col items-center px-6 gap-y-5 text-center">
      <div className={cn('flex items-center justify-center p-3.5 rounded-full', styles.circle)}>
        <Icon className={cn('size-7 animate-in zoom-in-50 duration-300', styles.icon)} />
      </div>

      <div className="flex flex-col gap-y-2">
        <p className="text-paragraph-semibold text-foreground">{title}</p>
        <p className="text-paragraph-sm text-muted-foreground">{description}</p>
      </div>

      {children}
    </div>
  );
}
