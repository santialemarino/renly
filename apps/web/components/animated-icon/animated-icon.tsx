import type { LucideIcon } from 'lucide-react';

import { cn } from '@repo/ui/lib';
import { DrawIcon } from '@/components/animated-icon/draw-icon';
import { BESPOKE_ICONS, FAMILY_CLASS, ICON_MOTION } from '@/components/animated-icon/registry';

interface AnimatedIconProps {
  icon: LucideIcon;
  className?: string;
}

/*
 * Drop-in replacement for a bare Lucide icon that gives it a bespoke, part-aware motion. The motion
 * plays while the nearest interactive ancestor marked `data-animate-icon` is hovered or keyboard-
 * focused (focus parity) and collapses under reduced motion — both handled by the shared @repo/ui
 * rules. The icon-to-motion mapping lives in registry.ts: a part-level bespoke component, a whole-glyph
 * family class, or the universal "draw itself in" fallback so no icon is left on a generic transform.
 * Consumers only add `data-animate-icon` to the interactive element (once per surface), then swap
 * `<Icon />` for `<AnimatedIcon icon={Icon} />`.
 */
export function AnimatedIcon({ icon: Icon, className }: AnimatedIconProps) {
  const Bespoke = BESPOKE_ICONS.get(Icon);
  if (Bespoke) return <Bespoke className={className} />;

  const family = ICON_MOTION.get(Icon);
  if (!family) return <DrawIcon icon={Icon} className={className} />;

  return <Icon aria-hidden className={cn(FAMILY_CLASS[family], className)} />;
}
