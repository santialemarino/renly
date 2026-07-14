import { TableHead } from '@repo/ui/components';
import { SortIcon } from '@/components/sort-icon';
import type { SortOrder } from '@/lib/api/types';

interface SortableTableHeadProps<T extends string> {
  label: string;
  column: T;
  sortBy: T | null;
  sortOrder: SortOrder;
  onSort: (column: T) => void;
}

// Sortable column header: the shared sort-button treatment (hover color shift + icon
// focus-bump via the group/sort focusable group) wrapping the column's SortIcon.
export function SortableTableHead<T extends string>({
  label,
  column,
  sortBy,
  sortOrder,
  onSort,
}: SortableTableHeadProps<T>) {
  return (
    <TableHead>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="group/sort flex items-center gap-x-1 hover:text-foreground transition-colors focus-visible:outline-none"
      >
        {label}
        <SortIcon active={sortBy === column} order={sortOrder} />
      </button>
    </TableHead>
  );
}
