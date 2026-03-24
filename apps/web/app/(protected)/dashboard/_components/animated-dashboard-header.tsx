'use client';

import { AnimatePresence, LayoutGroup, motion } from 'motion/react';

import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

interface AnimatedDashboardHeaderProps {
  subtitleKey: string;
  subtitle: React.ReactNode;
  warnings: React.ReactNode;
}

// Animates subtitle transitions (fade in/out when filter changes).
// Uses initial={false} so the first render is static — no animation on page load.
export function AnimatedDashboardHeader({
  subtitleKey,
  subtitle,
  warnings,
}: AnimatedDashboardHeaderProps) {
  return (
    <div className="flex flex-col gap-y-1">
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={subtitleKey}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: ANIMATION_DEFAULT }}
        >
          {subtitle}
        </motion.div>
      </AnimatePresence>
      {warnings}
    </div>
  );
}

interface AnimatedDashboardToolbarProps {
  backButton: React.ReactNode;
  search: React.ReactNode;
  periodPicker: React.ReactNode;
}

// Animates toolbar layout shifts: search bar smoothly resizes when back button appears/disappears,
// and period presets shift when custom picker expands.
export function AnimatedDashboardToolbar({
  backButton,
  search,
  periodPicker,
}: AnimatedDashboardToolbarProps) {
  return (
    <LayoutGroup>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        {backButton}
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="min-w-92 flex-1">
          {search}
        </motion.div>
        <motion.div
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          className="basis-full xl:basis-auto"
        >
          {periodPicker}
        </motion.div>
      </div>
    </LayoutGroup>
  );
}
