import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';

import { cn } from '@repo/ui/lib';
import type { SortOrder } from '@/lib/api/types';

interface SortIconProps {
  active: boolean;
  order: SortOrder;
}

// All three icons share the same grid cell; only one is visible at a time via opacity/scale.
export function SortIcon({ active, order }: SortIconProps) {
  const isAsc = active && order === 'asc';
  const isDesc = active && order === 'desc';
  return (
    <span className="grid shrink-0 group-focus-visible/sort:animate-focus-bump">
      <ChevronsUpDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-400 transition-all duration-200',
          active ? 'scale-0 opacity-0' : 'scale-100 opacity-100',
        )}
      />
      <ArrowUp
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isAsc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
      <ArrowDown
        className={cn(
          'col-start-1 row-start-1 size-3.5 text-blue-800 transition-all duration-200',
          isDesc ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
        )}
      />
    </span>
  );
}
