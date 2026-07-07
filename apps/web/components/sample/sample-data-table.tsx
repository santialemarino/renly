'use client';

import { useState } from 'react';
import { Eye, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@repo/ui/components';
import { dismissSamples } from '@/components/sample/sample-actions';
import { SampleDetailDialog, type SampleDetail } from '@/components/sample/sample-detail-dialog';

export interface SampleColumn<T> {
  header: string;
  cell: (row: T) => React.ReactNode;
  className?: string;
}

interface SampleDataTableProps<T extends { id: number }> {
  columns: SampleColumn<T>[];
  rows: T[];
  getDetail: (row: T) => SampleDetail;
}

// Renders first-run sample rows in place of an empty section: a banner marking them as examples
// (with a Clear that dismisses samples account-wide) plus a table mirroring the real one's columns.
// The rows are the client fixture — "View" opens a read-only detail, and nothing ever hits the API.
export function SampleDataTable<T extends { id: number }>({
  columns,
  rows,
  getDetail,
}: SampleDataTableProps<T>) {
  const t = useTranslations('common.sampleData');
  const [detail, setDetail] = useState<SampleDetail | null>(null);
  const [clearing, setClearing] = useState(false);

  async function handleClear() {
    if (clearing) return; // guard against a double-click while the dismiss is in flight
    setClearing(true);
    try {
      await dismissSamples();
    } catch {
      setClearing(false); // restore so the user can retry; the revalidate unmounts this on success
      toast.error(t('clearError'));
    }
  }

  return (
    <div className="flex flex-col gap-y-3">
      <div className="flex items-center justify-between p-3 gap-x-3 bg-blue-800/5 border border-blue-800/15 rounded-xl">
        <span className="flex items-center gap-x-2 text-paragraph-sm text-muted-foreground">
          <Sparkles className="size-4 shrink-0 text-blue-800" />
          {t('banner')}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          disabled={clearing}
          className="shrink-0"
        >
          {t('clear')}
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => (
              <TableHead key={col.header} className={col.className}>
                {col.header}
              </TableHead>
            ))}
            <TableHead className="w-20 text-center">{t('actions')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              {columns.map((col) => (
                <TableCell key={col.header} className={col.className}>
                  {col.cell(row)}
                </TableCell>
              ))}
              <TableCell className="text-center">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => setDetail(getDetail(row))}
                      aria-label={t('view')}
                    >
                      <Eye className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t('view')}</TooltipContent>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <SampleDetailDialog
        detail={detail}
        onOpenChange={(open) => {
          if (!open) setDetail(null);
        }}
      />
    </div>
  );
}
