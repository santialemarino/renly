'use client';

import type { ComponentType, ReactNode } from 'react';
import { motion, useReducedMotion, type HTMLMotionProps, type Variants } from 'motion/react';

import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

// px the content rises while fading in.
const REVEAL_RISE = 16;
// Seconds between staggered children entrances.
const REVEAL_STAGGER = 0.08;
// Scroll trigger — reveal once, firing slightly before the element is fully in view; never replays.
const REVEAL_VIEWPORT = { once: true, margin: '-10% 0px' } as const;
// Easing shared by every reveal so entrances feel uniform across the public surface.
const REVEAL_TRANSITION = { duration: ANIMATION_DEFAULT, ease: 'easeOut' } as const;

// The moving piece: fades up into place. Transition is set on the element (or inherited stagger delay).
const itemVariants: Variants = {
  hidden: { opacity: 0, y: REVEAL_RISE },
  visible: { opacity: 1, y: 0 },
};

// The orchestrator: stays put, only staggers its children's entrances.
const containerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: REVEAL_STAGGER } },
};

/*
 * Reduced-motion variants: content is always fully visible with no movement. We keep rendering a
 * motion element (rather than swapping to a plain tag) so motion clears the opacity:0 it inlines
 * during SSR — a plain element would leave that server style in place and hide the content.
 */
const staticItemVariants: Variants = {
  hidden: { opacity: 1, y: 0 },
  visible: { opacity: 1, y: 0 },
};

const staticContainerVariants: Variants = {
  hidden: {},
  visible: {},
};

const MOTION_TAGS = {
  div: motion.div,
  section: motion.section,
  ol: motion.ol,
  li: motion.li,
} as const;

type RevealTag = keyof typeof MOTION_TAGS;

interface RevealBaseProps {
  as?: RevealTag;
  className?: string;
  children: ReactNode;
}

// Resolves the motion component for a tag, typed loosely so the shared motion props all type-check.
function motionTag(as: RevealTag) {
  return MOTION_TAGS[as] as ComponentType<HTMLMotionProps<'div'>>;
}

interface RevealProps extends RevealBaseProps {
  // Animate on mount (above-the-fold content) instead of when scrolled into view.
  onLoad?: boolean;
  // Seconds to wait before the reveal starts.
  delay?: number;
}

// Single-block reveal: fades up on scroll-in (or on mount with onLoad). Reduced motion shows it instantly.
export function Reveal({
  as = 'div',
  onLoad = false,
  delay = 0,
  className,
  children,
}: RevealProps) {
  const reduced = useReducedMotion();
  const MotionTag = motionTag(as);
  const trigger = onLoad
    ? { animate: 'visible' }
    : { whileInView: 'visible', viewport: REVEAL_VIEWPORT };

  return (
    <MotionTag
      className={className}
      variants={reduced ? staticItemVariants : itemVariants}
      initial="hidden"
      transition={{ ...REVEAL_TRANSITION, delay }}
      {...trigger}
    >
      {children}
    </MotionTag>
  );
}

interface RevealGroupProps extends RevealBaseProps {
  // Stagger the children on mount instead of when scrolled into view.
  onLoad?: boolean;
}

// Stagger orchestrator: reveals its RevealItem children one after another. Pair with RevealItem.
export function RevealGroup({ as = 'div', onLoad = false, className, children }: RevealGroupProps) {
  const reduced = useReducedMotion();
  const MotionTag = motionTag(as);
  const trigger = onLoad
    ? { animate: 'visible' }
    : { whileInView: 'visible', viewport: REVEAL_VIEWPORT };

  return (
    <MotionTag
      className={className}
      variants={reduced ? staticContainerVariants : containerVariants}
      initial="hidden"
      {...trigger}
    >
      {children}
    </MotionTag>
  );
}

// One staggered child of a RevealGroup. Inherits the hidden/visible state from its parent group.
export function RevealItem({ as = 'div', className, children }: RevealBaseProps) {
  const reduced = useReducedMotion();
  const MotionTag = motionTag(as);

  return (
    <MotionTag
      className={className}
      variants={reduced ? staticItemVariants : itemVariants}
      transition={REVEAL_TRANSITION}
    >
      {children}
    </MotionTag>
  );
}
