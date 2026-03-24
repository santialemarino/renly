'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

interface DashboardToolbarProps {
  isFiltered: boolean;
}

export function DashboardToolbar({ isFiltered }: DashboardToolbarProps) {
  const t = useTranslations('dashboard');
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleBack() {
    // Preserve date range params when clearing the filter.
    const qs = new URLSearchParams();
    const period = searchParams.get('period');
    const startDate = searchParams.get('start_date');
    const endDate = searchParams.get('end_date');
    if (period) qs.set('period', period);
    if (startDate) qs.set('start_date', startDate);
    if (endDate) qs.set('end_date', endDate);
    const query = qs.toString();
    router.push(query ? `${ROUTES.dashboard}?${query}` : ROUTES.dashboard, { scroll: false });
  }

  return (
    <AnimatePresence initial={false}>
      {isFiltered && (
        <motion.div
          layout
          initial={{ opacity: 0, width: 0 }}
          animate={{ opacity: 1, width: 'auto' }}
          exit={{ opacity: 0, width: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
          className="shrink-0 overflow-hidden"
        >
          <Button variant="ghost" size="sm" className="whitespace-nowrap" onClick={handleBack}>
            <ArrowLeft className="size-4" />
            {t('toolbar.backToFull')}
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
