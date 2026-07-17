'use client';

import { useLocale, useTranslations } from 'next-intl';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import type { Feedback } from '@/lib/api/feedback';
import type { FeedbackCategory } from '@/lib/constants/feedback';
import { formatTimestampDate } from '@/lib/utils/format';

// Badge tone per category (outline base — quiet status chips).
const CATEGORY_CLASS: Record<FeedbackCategory, string> = {
  bug: 'bg-red-50 border-red-200 text-red-700',
  idea: 'bg-blue-50 border-blue-200 text-blue-800',
  question: 'bg-amber-50 border-amber-200 text-amber-700',
  other: 'text-muted-foreground',
};

interface AdminFeedbackProps {
  feedback: Feedback[];
}

export function AdminFeedback({ feedback }: AdminFeedbackProps) {
  const locale = useLocale();
  const t = useTranslations('adminFeedback');
  const tFeedback = useTranslations('feedback');

  if (feedback.length === 0) {
    return (
      <div className="flex items-center justify-center w-full max-w-4xl p-6 border border-dashed rounded-lg">
        <p className="text-paragraph-sm text-muted-foreground">{t('empty')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full max-w-4xl gap-y-6">
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
                {formatTimestampDate(item.createdAt, locale)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
