'use client';

import { Loader2, Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { useQuickAddControls } from '@/app/(protected)/_components/quick-add-context';

/*
 * The global quick-add's button (X4) — only the button. The forms it opens belong to
 * `QuickAddProvider`, which the protected layout renders outside the sidebar.
 *
 * It lives in the sidebar because the app has no top bar: every protected page owns its full vertical
 * space and renders its own PageHeader, so the sidebar is the persistent shell — the same reasoning the
 * notification bell records. What must NOT live there is anything that has to outlast a tap on this
 * button: below `md` the sidebar is a Sheet, opening a form closes it, and a closed Sheet is unmounted.
 */
export function QuickAddTrigger() {
  const t = useTranslations('sidebar');
  const { open, loading } = useQuickAddControls();

  return (
    <Button
      blue
      size="lg"
      onClick={open}
      disabled={loading}
      aria-haspopup="dialog"
      data-testid="quick-add-trigger"
      className="w-full justify-center gap-2 [&_svg]:size-5 text-paragraph-medium"
    >
      {/* Both icons share one grid cell, so the swap crossfades instead of reflowing the label. */}
      <span className="grid shrink-0">
        <Plus
          className={cn(
            'col-start-1 row-start-1 transition-all duration-200',
            loading ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
          )}
        />
        <Loader2
          className={cn(
            'col-start-1 row-start-1 animate-spin transition-all duration-200',
            loading ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
          )}
        />
      </span>
      <span>{t('nav.quickAdd')}</span>
    </Button>
  );
}
