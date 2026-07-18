'use client';

import { useEffect, useRef } from 'react';
import type { LucideIcon } from 'lucide-react';

/*
 * Universal "draw itself in" motion for any Lucide icon. Renders the real lucide-react icon, then
 * normalises every sub-shape to `pathLength=1` and tags it with `aicon-draw` (+ a per-part index) so
 * the shared rule draws each part in, staggered, whenever the nearest `data-animate-icon` ancestor is
 * hovered or keyboard-focused. This is the catch-all family — icons without a more specific motion
 * animate their own strokes, so nothing falls back to a generic transform. Reduced motion collapses
 * it; only stroke-dashoffset animates (no layout shift). SSR renders the plain icon (no dasharray),
 * so there is no flash of a hidden icon before hydration.
 */
export function DrawIcon({ icon: Icon, className }: { icon: LucideIcon; className?: string }) {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    svg.querySelectorAll<SVGElement>(':scope > *').forEach((el, index) => {
      el.setAttribute('pathLength', '1');
      el.style.setProperty('--aicon-i', String(index));
      el.classList.add('aicon-draw');
    });
  }, []);

  return <Icon ref={ref} aria-hidden className={className} />;
}
