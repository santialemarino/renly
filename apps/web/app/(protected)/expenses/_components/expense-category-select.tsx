'use client';

import { Tag } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { sortExpenseCategoriesByLabel } from '@/lib/utils/categories';

interface ExpenseCategorySelectProps {
  value: string;
  onValueChange: (value: string) => void;
  surface?: boolean;
  className?: string;
}

export function ExpenseCategorySelect({
  value,
  onValueChange,
  surface = false,
  className,
}: ExpenseCategorySelectProps) {
  const locale = useLocale();
  const t = useTranslations('expenses');
  const tCommon = useTranslations('common');

  return (
    <FilterCombobox
      items={sortExpenseCategoriesByLabel((key) => t(key), locale)}
      value={value}
      onValueChange={onValueChange}
      labelFor={(cat) => t(`categories.${cat}`)}
      allLabel={tCommon('allCategories')}
      icon={Tag}
      align="start"
      surface={surface}
      className={className}
    />
  );
}
