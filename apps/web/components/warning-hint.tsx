'use client';

import { AlertTriangle } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { Hint, Separator } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

const ANIMATION_DURATION = 0.25;

interface WarningHintProps {
  show: boolean;
  children: React.ReactNode;
  className?: string;
  // Show a separator above the hint.
  separator?: boolean;
  // Parent gap in px to compensate during exit animation. Prevents content shift.
  parentGap?: number;
}

export function WarningHint({
  show,
  children,
  className,
  separator = false,
  parentGap = 4,
}: WarningHintProps) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: ANIMATION_DURATION }}
          style={{ overflow: 'hidden', marginTop: -parentGap }}
        >
          <div className="flex flex-col" style={{ paddingTop: parentGap, gap: parentGap }}>
            {separator && <Separator />}
            <div className={cn('flex items-center gap-x-2', className)}>
              <AlertTriangle className="size-4 shrink-0 text-amber-500" />
              <Hint className="text-amber-600 whitespace-pre-line">{children}</Hint>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
