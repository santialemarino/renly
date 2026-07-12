'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';

import { Button } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ANIMATION_FAST } from '@/lib/constants/animations';

const COPY_RESET_MS = 2000;

interface CopyButtonProps {
  value: string;
  className?: string;
}

// Button that copies a value to clipboard with animated check feedback.
export function CopyButton({ value, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (copied) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), COPY_RESET_MS);
  }

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={handleCopy}
      className={cn(
        'transition-all duration-200',
        copied && 'hover:bg-background hover:text-foreground cursor-default',
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        {copied ? (
          <motion.div
            key="check"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: ANIMATION_FAST }}
          >
            <Check className="size-4 text-emerald-600" />
          </motion.div>
        ) : (
          <motion.div
            key="copy"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: ANIMATION_FAST }}
          >
            <Copy className="size-4" />
          </motion.div>
        )}
      </AnimatePresence>
    </Button>
  );
}
