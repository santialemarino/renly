'use client';

import { Tag } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { sortIncomeCategoriesByLabel } from '@/lib/utils/categories';

interface IncomeCategorySelectProps {
  value: string;
  onValueChange: (value: string) => void;
  surface?: boolean;
  className?: string;
}

export function IncomeCategorySelect({
  value,
  onValueChange,
  surface = false,
  className,
}: IncomeCategorySelectProps) {
  const locale = useLocale();
  const tCommon = useTranslations('common');

  return (
    <FilterCombobox
      items={sortIncomeCategoriesByLabel((key) => tCommon(key), locale)}
      value={value}
      onValueChange={onValueChange}
      labelFor={(cat) => tCommon(`categories.${cat}`)}
      allLabel={tCommon('allCategories')}
      icon={Tag}
      align="start"
      surface={surface}
      className={className}
    />
  );
}
