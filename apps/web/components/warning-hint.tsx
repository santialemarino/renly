'use client';

import { AlertTriangle } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { Hint } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';

const ANIMATION_DURATION = 0.25;

interface WarningHintProps {
  show: boolean;
  children: React.ReactNode;
  className?: string;
}

export function WarningHint({ show, children, className }: WarningHintProps) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: ANIMATION_DURATION }}
          className="overflow-hidden"
        >
          <div className={cn('flex items-center gap-x-2', className)}>
            <AlertTriangle className="size-4 shrink-0 text-amber-500" />
            <Hint className="text-amber-600 whitespace-pre-line">{children}</Hint>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
