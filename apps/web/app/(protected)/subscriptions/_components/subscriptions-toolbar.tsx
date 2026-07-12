'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Archive, Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button, Pill, SearchInput } from '@repo/ui/components';
import { SubscriptionFormDialog } from '@/app/(protected)/subscriptions/_components/subscription-form-dialog';
import { ROUTES } from '@/config/routes';
import type { CreditCard } from '@/lib/api/credit-cards';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';

interface SubscriptionsToolbarProps {
  preferredCurrencies?: string[];
  supportedCurrencies?: string[];
  creditCards?: CreditCard[];
}

export function SubscriptionsToolbar({
  preferredCurrencies,
  supportedCurrencies,
  creditCards,
}: SubscriptionsToolbarProps) {
  const t = useTranslations('subscriptions');
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const [, startTransition] = useTransition();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  const showArchived = searchParams.get('show_archived') === 'true';

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null || val === '') {
        params.delete(key);
      } else {
        params.set(key, val);
      }
    });
    startTransition(() => router.push(`${ROUTES.subscriptions}?${params.toString()}`));
  }

  useEffect(() => {
    const timer = setTimeout(() => navigate({ search }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  return (
    <LayoutGroup>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }} className="min-w-0 flex-1">
          <SearchInput
            aria-label="Search subscriptions"
            placeholder={t('toolbar.searchPlaceholder')}
            value={search}
            surface
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
          />
        </motion.div>

        <motion.div
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          className="flex flex-wrap basis-full md:basis-auto items-center gap-x-3 gap-y-2"
        >
          <Pill
            active={showArchived}
            aria-pressed={showArchived}
            onClick={() => navigate({ show_archived: showArchived ? null : 'true' })}
            className="min-w-fit flex-1"
          >
            <Archive className="size-4" />
            {t('toolbar.showArchived')}
          </Pill>
          <Button blue onClick={() => setCreateOpen(true)} className="min-w-fit flex-1">
            <Plus className="size-4" />
            {t('toolbar.add')}
          </Button>
        </motion.div>

        <SubscriptionFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          preferredCurrencies={preferredCurrencies}
          supportedCurrencies={supportedCurrencies}
          creditCards={creditCards}
          onSuccess={() => router.refresh()}
        />
      </div>
    </LayoutGroup>
  );
}
