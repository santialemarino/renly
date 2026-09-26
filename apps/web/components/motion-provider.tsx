'use client';

import { MotionConfig } from 'motion/react';

/*
 * The app-wide motion/react config, rendered once by the root layout around every surface (auth,
 * protected, public, the not-found page and the root-level overlays beside them).
 *
 * `reducedMotion="user"` is what makes every motion/react animation honour
 * `prefers-reduced-motion: reduce` by default: transform and layout animations (x/y, scale, height
 * reveals) jump to their end state, while opacity and colour still animate. Without it motion/react
 * defaults to "never" and plays every animation in full regardless of the OS setting. A client
 * component because MotionConfig is one and the root layout is a server component.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
