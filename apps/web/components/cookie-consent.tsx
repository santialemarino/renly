'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { InlineLink } from '@/components/inline-link';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

const STORAGE_KEY = 'cookie-consent-dismissed';

// Site-wide cookie/consent notice (SHELL-11). Renly only uses essential cookies (auth session,
// locale, currency preferences), so this is an informational acknowledgement, not a tracking
// opt-in. The choice is persisted in localStorage, mirroring the dismissable-hint pattern.
export function CookieConsent() {
  const t = useTranslations('common.cookieConsent');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(localStorage.getItem(STORAGE_KEY) !== 'true');
  }, []);

  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setVisible(false);
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="fixed inset-x-0 bottom-0 z-50 flex justify-center p-4"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ duration: ANIMATION_DEFAULT }}
        >
          <div className="flex flex-col w-full items-start p-4 gap-y-3 bg-background border border-neutral-200 rounded-xl shadow-lg sm:flex-row sm:w-fit sm:max-w-full sm:items-center sm:gap-x-4">
            <p className="text-paragraph-sm text-muted-foreground whitespace-pre-line">
              {t('message')}{' '}
              <InlineLink href={ROUTES.privacy} color="blue">
                {t('learnMore')}
              </InlineLink>
            </p>
            <Button blue size="sm" className="shrink-0 w-full sm:w-auto" onClick={handleDismiss}>
              {t('accept')}
            </Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
