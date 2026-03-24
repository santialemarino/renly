'use client';

import { FolderOpen } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { ComboboxMultiSelect } from '@/components/combobox-multi-select';

interface GroupMultiSelectProps {
  groups: { id: number; name: string }[];
  selectedIds: number[];
  onToggle: (groupId: number) => void;
  surface?: boolean;
  className?: string;
}

export function GroupMultiSelect({
  groups,
  selectedIds,
  onToggle,
  surface = false,
  className,
}: GroupMultiSelectProps) {
  const tCommon = useTranslations('common');

  const count = selectedIds.length;
  const label = count > 0 ? tCommon('groupFilter.selected', { count }) : tCommon('groupFilter.all');

  return (
    <ComboboxMultiSelect
      items={groups.map((g) => ({ id: g.id, label: g.name }))}
      selectedIds={selectedIds}
      onToggle={onToggle}
      placeholder={label}
      searchPlaceholder={tCommon('groupFilter.search')}
      emptyMessage={tCommon('groupFilter.empty')}
      icon={<FolderOpen className="size-4 shrink-0" />}
      surface={surface}
      className={className}
    />
  );
}
