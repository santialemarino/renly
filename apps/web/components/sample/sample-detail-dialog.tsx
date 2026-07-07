'use client';

import { useTranslations } from 'next-intl';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';

export interface SampleDetail {
  title: string;
  fields: { label: string; value: React.ReactNode }[];
}

// Read-only detail for a first-run sample row. Mirrors the "click a row to see it" affordance of the
// real tables, but the data is the client fixture — there's no fetch and nothing to persist.
export function SampleDetailDialog({
  detail,
  onOpenChange,
}: {
  detail: SampleDetail | null;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations('common.sampleData');
  return (
    <Dialog open={detail !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{detail?.title}</DialogTitle>
          <DialogDescription>{t('detailNotice')}</DialogDescription>
        </DialogHeader>
        <dl className="flex flex-col gap-y-3">
          {detail?.fields.map((field) => (
            <div key={field.label} className="flex items-center justify-between gap-x-4">
              <dt className="text-paragraph-sm text-muted-foreground">{field.label}</dt>
              <dd className="text-paragraph-sm-medium">{field.value}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
