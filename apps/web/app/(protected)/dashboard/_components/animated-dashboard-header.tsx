'use client';

import { AnimatePresence, LayoutGroup, motion } from 'motion/react';

const ANIMATION_DURATION = 0.25;

interface AnimatedDashboardHeaderProps {
  subtitleKey: string;
  subtitle: React.ReactNode;
  warnings: React.ReactNode;
  backButton: React.ReactNode;
  search: React.ReactNode;
}

// Animates subtitle transitions (fade in/out when filter changes) and toolbar layout shifts
// (search bar smoothly resizes when back button appears/disappears).
export function AnimatedDashboardHeader({
  subtitleKey,
  subtitle,
  warnings,
  backButton,
  search,
}: AnimatedDashboardHeaderProps) {
  return (
    <div className="flex flex-col gap-y-2">
      <div className="flex flex-col gap-y-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={subtitleKey}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: ANIMATION_DURATION }}
          >
            {subtitle}
          </motion.div>
        </AnimatePresence>
        {warnings}
      </div>
      <LayoutGroup>
        <div className="flex items-center gap-x-2">
          {backButton}
          <motion.div
            layout
            transition={{ duration: ANIMATION_DURATION }}
            className="flex-1 min-w-0"
          >
            {search}
          </motion.div>
        </div>
      </LayoutGroup>
    </div>
  );
}
