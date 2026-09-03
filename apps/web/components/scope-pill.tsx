'use client';

import { Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { SegmentedPills } from '@/components/segmented-pills';
import type { ListScope } from '@/lib/api/types';

const SCOPES: readonly ListScope[] = ['all', 'private', 'shared'];

/*
 * X2's scope filter: All / Yours / Shared, in every scope-aware list toolbar.
 *
 * THE rule, and it is not negotiable: this FILTERS, it is never a mode. A persistent mode would let
 * somebody misread every number on screen, because the page would keep showing a subset while looking
 * like the whole; a filter cannot, because "All" is the default and the sections beneath it are all on
 * screen at once. So the control has no memory of its own — the selection lives in the URL, where it
 * is visible, shareable and gone on the next visit.
 *
 * Three values rather than one per group: the count must not grow with how many households somebody
 * shares money with, and the section headers already name each one.
 *
 * Rendered ONLY where the caller belongs to a group (the page decides), so a solo user — which is
 * every public user at launch — sees no added control at all.
 */
export function ScopePill({
  value,
  onChange,
}: {
  value: ListScope;
  onChange: (scope: ListScope) => void;
}) {
  const tCommon = useTranslations('common');

  return (
    <SegmentedPills
      value={value}
      options={SCOPES}
      onChange={onChange}
      label={tCommon('scope.label')}
      labelFor={(scope) => tCommon(`scope.${scope}`)}
      iconFor={(scope) => (scope === 'shared' ? Users : undefined)}
    />
  );
}
