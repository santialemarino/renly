'use client';

import { Tag } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { sortCategoriesByLabel } from '@/lib/utils/categories';

interface CategorySelectProps {
  value: string;
  onValueChange: (value: string) => void;
  surface?: boolean;
  className?: string;
}

export function CategorySelect({
  value,
  onValueChange,
  surface = false,
  className,
}: CategorySelectProps) {
  const locale = useLocale();
  const tCommon = useTranslations('common');

  return (
    <FilterCombobox
      items={sortCategoriesByLabel(tCommon, locale)}
      value={value}
      onValueChange={onValueChange}
      labelFor={(cat) => tCommon(`categories.${cat}`)}
      allLabel={tCommon('allCategories')}
      icon={Tag}
      align="end"
      surface={surface}
      className={className}
    />
  );
}
