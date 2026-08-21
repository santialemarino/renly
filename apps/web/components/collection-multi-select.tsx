'use client';

import { FolderOpen } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { ComboboxMultiSelect } from '@/components/combobox-multi-select';

interface CollectionMultiSelectProps {
  collections: { id: number; name: string }[];
  selectedIds: number[];
  onToggle: (collectionId: number) => void;
  surface?: boolean;
  className?: string;
}

export function CollectionMultiSelect({
  collections,
  selectedIds,
  onToggle,
  surface = false,
  className,
}: CollectionMultiSelectProps) {
  const tCommon = useTranslations('common');

  const count = selectedIds.length;
  const label =
    count > 0 ? tCommon('collectionFilter.selected', { count }) : tCommon('collectionFilter.all');

  return (
    <ComboboxMultiSelect
      items={collections.map((c) => ({ id: c.id, label: c.name }))}
      selectedIds={selectedIds}
      onToggle={onToggle}
      placeholder={label}
      searchPlaceholder={tCommon('collectionFilter.search')}
      emptyMessage={tCommon('collectionFilter.empty')}
      icon={<FolderOpen className="size-4 shrink-0" />}
      surface={surface}
      className={className}
    />
  );
}
