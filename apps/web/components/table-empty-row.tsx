import type { LucideIcon } from 'lucide-react';

import { TableCell, TableRow } from '@repo/ui/components';
import { EmptyState } from '@/components/empty-state';

interface TableEmptyRowProps {
  colSpan: number;
  firstRun?: boolean;
  icon: LucideIcon;
  title: string;
  description: string;
  plain: string;
}

/*
 * The empty row for a data table: a first-run teaching EmptyState, or the plain "no rows" line for a
 * returning/onboarded user (or a filtered-empty view). One component so the plain-cell styling can't
 * drift across the list pages.
 */
export function TableEmptyRow({
  colSpan,
  firstRun,
  icon,
  title,
  description,
  plain,
}: TableEmptyRowProps) {
  if (firstRun) {
    return (
      <TableRow>
        <TableCell colSpan={colSpan} className="p-0">
          <EmptyState icon={icon} title={title} description={description} />
        </TableCell>
      </TableRow>
    );
  }
  return (
    <TableRow>
      <TableCell colSpan={colSpan} className="py-10 rounded-sm text-center text-muted-foreground">
        {plain}
      </TableCell>
    </TableRow>
  );
}
