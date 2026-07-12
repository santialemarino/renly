'use client';

import { CreditCard } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { FilterCombobox } from '@/components/filter-combobox';
import { PAYMENT_METHODS } from '@/lib/constants/categories';

interface PaymentMethodSelectProps {
  value: string;
  onValueChange: (value: string) => void;
  surface?: boolean;
  className?: string;
}

export function PaymentMethodSelect({
  value,
  onValueChange,
  surface = false,
  className,
}: PaymentMethodSelectProps) {
  const t = useTranslations('expenses');

  return (
    <FilterCombobox
      items={PAYMENT_METHODS}
      value={value}
      onValueChange={onValueChange}
      labelFor={(method) => t(`paymentMethods.${method}`)}
      allLabel={t('toolbar.allPaymentMethods')}
      icon={CreditCard}
      align="end"
      surface={surface}
      className={className}
    />
  );
}
