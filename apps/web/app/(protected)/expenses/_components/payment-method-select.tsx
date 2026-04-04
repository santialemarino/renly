'use client';

import { useState } from 'react';
import { Check, ChevronsUpDown, CreditCard } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { CATEGORY_ALL } from '@/lib/constants/api-constants';
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
  const tCommon = useTranslations('common');
  const [open, setOpen] = useState(false);

  const isAll = value === CATEGORY_ALL;
  const label = isAll ? t('toolbar.allPaymentMethods') : t(`paymentMethods.${value}`);

  const items = [CATEGORY_ALL, ...PAYMENT_METHODS];

  function handleSelect(selected: string) {
    onValueChange(selected);
    setOpen(false);
  }

  return (
    <div className={className}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className={cn(
              'h-9 w-full justify-between gap-x-2 border-border px-3 shadow-xs',
              'text-paragraph-sm font-normal',
              isAll ? 'text-muted-foreground' : 'text-foreground',
              'hover:border-ring',
              'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
              surface ? 'bg-background' : 'bg-input',
            )}
          >
            <span className="flex items-center gap-x-2 truncate">
              <CreditCard className="size-4 shrink-0" />
              {label}
            </span>
            <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="sm:min-w-78 w-(--radix-popover-trigger-width) p-0"
          align="end"
          sideOffset={8}
        >
          <Command>
            <CommandList>
              <CommandEmpty>{tCommon('groupFilter.empty')}</CommandEmpty>
              <CommandGroup>
                {items.map((method) => {
                  const isSelected = value === method;
                  const methodLabel =
                    method === CATEGORY_ALL
                      ? t('toolbar.allPaymentMethods')
                      : t(`paymentMethods.${method}`);
                  return (
                    <CommandItem
                      key={method}
                      value={methodLabel}
                      onSelect={() => handleSelect(method)}
                    >
                      <Check
                        className={cn(
                          'size-4 shrink-0 transition-all duration-150',
                          isSelected ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                        )}
                      />
                      {methodLabel}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
