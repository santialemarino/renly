'use client';

import { useTranslations } from 'next-intl';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { TablePagination } from '@/components/table-pagination';
import { ROUTES } from '@/config/routes';
import type { Feedback } from '@/lib/api/feedback';
import type { FeedbackCategory } from '@/lib/constants/feedback';
import { useSearchParamsNavigation } from '@/lib/hooks/use-search-params-navigation';
import { useFormatters } from '@/lib/i18n/formatters';

// Badge tone per category (outline base — quiet status chips).
const CATEGORY_CLASS: Record<FeedbackCategory, string> = {
  bug: 'bg-red-50 border-red-200 text-red-700',
  idea: 'bg-blue-50 border-blue-200 text-blue-800',
  question: 'bg-amber-50 border-amber-200 text-amber-700',
  other: 'text-muted-foreground',
};

interface AdminFeedbackProps {
  // One page of feedback, with the total across every page and the size the server used. Paginated
  // since SEC-11: this list spans every user, so it grows with the user base.
  feedback: Feedback[];
  total: number;
  page: number;
  pageSize: number;
}

export function AdminFeedback({ feedback, total, page, pageSize }: AdminFeedbackProps) {
  const fmt = useFormatters();
  const t = useTranslations('adminFeedback');
  const { navigate, isPending } = useSearchParamsNavigation(ROUTES.adminFeedback);
  const tFeedback = useTranslations('feedback');

  /*
   * `total` rather than the page's own length, and the difference is a page past the end: nobody has
   * ever sent feedback is a different fact from this page holding none of it, and answering the second
   * with the first strands the reader on `?page=9` with no pager to step back with.
   */
  if (total === 0) {
    return (
      <div className="flex items-center justify-center w-full max-w-4xl p-6 border border-dashed rounded-lg">
        <p className="text-paragraph-sm text-muted-foreground">{t('empty')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full max-w-4xl gap-y-6">
      <div className={isPending ? 'opacity-60 pointer-events-none transition-opacity' : ''}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('table.from')}</TableHead>
              <TableHead>{t('table.category')}</TableHead>
              <TableHead>{t('table.message')}</TableHead>
              <TableHead>{t('table.date')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {feedback.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="text-paragraph-sm-medium">{item.email}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={CATEGORY_CLASS[item.category]}>
                    {tFeedback(`categories.${item.category}`)}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-md whitespace-pre-wrap text-muted-foreground">
                  {item.message}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {fmt.timestampDate(item.createdAt)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <TablePagination
        page={page}
        totalPages={Math.max(1, Math.ceil(total / pageSize))}
        totalLabel={t('table.total', { total })}
        onPageChange={(next) => navigate({ page: next === 1 ? null : String(next) })}
      />
    </div>
  );
}
