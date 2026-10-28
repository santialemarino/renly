'use client';

import { RotateCw } from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ANIMATION_FAST } from '@/lib/constants/animations';

interface PagedListLoadErrorProps {
  // Re-fetches the page that failed.
  onRetry: () => void;
  className?: string;
}

/*
 * What an expandable row's paged list shows after its load failed, in place of the empty line: an empty
 * line there would claim the list has nothing in it. Rendered as a keyed child of the panel's
 * `AnimatePresence mode="wait"`, so it crossfades like the loading, empty and table states. `role="alert"`
 * announces the failure when it appears.
 */
export function PagedListLoadError({ onRetry, className }: PagedListLoadErrorProps) {
  const t = useTranslations('common.pagedList');

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: ANIMATION_FAST }}
      className={cn('flex flex-wrap items-center gap-x-3 gap-y-2', className)}
      data-testid="paged-list-load-error"
    >
      <p role="alert" className="text-paragraph-sm text-muted-foreground">
        {t('loadError')}
      </p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <RotateCw className="size-3.5" />
        {t('retry')}
      </Button>
    </motion.div>
  );
}
