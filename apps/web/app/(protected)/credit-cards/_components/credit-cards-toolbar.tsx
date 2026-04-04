'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button, SearchInput } from '@repo/ui/components';
import { CreditCardFormDialog } from '@/app/(protected)/credit-cards/_components/credit-card-form-dialog';
import { ROUTES } from '@/config/routes';
import { ANIMATION_DEFAULT, DEBOUNCE_MS } from '@/lib/constants/animations';

export function CreditCardsToolbar({ preferredCurrencies }: { preferredCurrencies?: string[] }) {
  const t = useTranslations('creditCards');
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  const [, startTransition] = useTransition();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') ?? '');

  function navigate(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParamsRef.current.toString());
    Object.entries(overrides).forEach(([key, val]) => {
      if (val === null || val === '') {
        params.delete(key);
      } else {
        params.set(key, val);
      }
    });
    startTransition(() => router.push(`${ROUTES.creditCards}?${params.toString()}`));
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
            aria-label="Search credit cards"
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
          className="flex items-center basis-full md:basis-auto"
        >
          <Button blue onClick={() => setCreateOpen(true)} className="min-w-fit flex-1">
            <Plus className="size-4" />
            {t('toolbar.addCard')}
          </Button>
        </motion.div>

        <CreditCardFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          preferredCurrencies={preferredCurrencies}
          onSuccess={() => router.refresh()}
        />
      </div>
    </LayoutGroup>
  );
}
