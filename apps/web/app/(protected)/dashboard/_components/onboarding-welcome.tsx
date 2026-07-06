'use client';

import { useState, useTransition } from 'react';
import { CircleDollarSign, Sparkles, TrendingUp, Upload, X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Card } from '@repo/ui/components';
import { completeOnboarding } from '@/app/(protected)/dashboard/_components/onboarding-welcome-actions';
import { LinkCard } from '@/components/link-card';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

// First-run welcome shown on the dashboard until onboarding is completed. Dismissing persists the flag
// (server-side) so it never returns; the CTAs point new users at the highest-value first actions.
export function OnboardingWelcome() {
  const t = useTranslations('dashboard.onboarding');
  const [dismissed, setDismissed] = useState(false);
  const [, startDismiss] = useTransition();

  function handleDismiss() {
    setDismissed(true); // optimistic — hide immediately; the server flag keeps it hidden on reload
    startDismiss(async () => {
      try {
        await completeOnboarding();
      } catch {
        setDismissed(false); // restore on failure so the user can retry
        toast.error(t('dismissError'));
      }
    });
  }

  return (
    <AnimatePresence initial={false}>
      {!dismissed && (
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: ANIMATION_DEFAULT }}
        >
          <Card compact className="relative gap-y-4 p-6">
            <button
              type="button"
              onClick={handleDismiss}
              aria-label={t('dismiss')}
              className="group/dismiss flex absolute top-3 right-3 p-1 rounded-md text-muted-foreground outline-none transition-colors duration-200 cursor-pointer hover:text-foreground focus-visible:text-foreground"
            >
              <X className="size-4 group-focus-visible/dismiss:animate-focus-bump-soft" />
            </button>

            <div className="flex flex-col gap-y-1 pr-8">
              <span className="flex items-center gap-x-2 text-heading-5">
                <Sparkles className="size-5 text-blue-800" />
                {t('title')}
              </span>
              <span className="text-paragraph-sm text-muted-foreground">{t('subtitle')}</span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <LinkCard
                href={ROUTES.investments}
                icon={TrendingUp}
                label={t('addInvestment.label')}
                hint={t('addInvestment.hint')}
              />
              <LinkCard
                href={`${ROUTES.data}?type=investments`}
                icon={Upload}
                label={t('import.label')}
                hint={t('import.hint')}
              />
              <LinkCard
                href={ROUTES.preferences}
                icon={CircleDollarSign}
                label={t('currencies.label')}
                hint={t('currencies.hint')}
              />
            </div>
          </Card>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
