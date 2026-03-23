'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';

const ANIMATION_DURATION = 0.25;

interface DashboardToolbarProps {
  isFiltered: boolean;
}

export function DashboardToolbar({ isFiltered }: DashboardToolbarProps) {
  const t = useTranslations('dashboard');
  const router = useRouter();

  return (
    <AnimatePresence initial={false}>
      {isFiltered && (
        <motion.div
          layout
          initial={{ opacity: 0, width: 0 }}
          animate={{ opacity: 1, width: 'auto' }}
          exit={{ opacity: 0, width: 0 }}
          transition={{ duration: ANIMATION_DURATION }}
          className="shrink-0 overflow-hidden"
        >
          <Button
            variant="ghost"
            size="sm"
            className="whitespace-nowrap"
            onClick={() => router.push(ROUTES.dashboard, { scroll: false })}
          >
            <ArrowLeft className="size-4" />
            {t('toolbar.backToFull')}
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
