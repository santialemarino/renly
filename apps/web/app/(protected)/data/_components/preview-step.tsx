'use client';

import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import type { ImportPreview, ImportRowStatus } from '@/lib/api/imports';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';

// motion-wrapped Button so `layout` animates the button's width when its label (count) changes.
const MotionButton = motion.create(Button);

const STATUS_STYLES: Record<ImportRowStatus, string> = {
  valid: 'text-green-700',
  duplicate: 'text-amber-600',
  invalid: 'text-destructive',
};

interface PreviewStepProps {
  preview: ImportPreview;
  entity: string;
  importDuplicates: boolean;
  onToggleDuplicates: (value: boolean) => void;
  onConfirm: () => void;
  confirming: boolean;
  onReset: () => void;
}

export function PreviewStep({
  preview,
  entity,
  importDuplicates,
  onToggleDuplicates,
  onConfirm,
  confirming,
  onReset,
}: PreviewStepProps) {
  const t = useTranslations('data');
  const { summary, fields, rows } = preview;
  const importable = summary.valid + (importDuplicates ? summary.duplicate : 0);
  const confirmLabel = confirming
    ? t('import.preview.importing')
    : t('import.preview.confirm', { count: importable, entity });

  return (
    <div className="flex flex-col gap-y-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-paragraph-sm">
        <span>{t('import.preview.summary', { total: summary.total })}</span>
        <span className="text-green-700">
          {t('import.preview.valid', { count: summary.valid })}
        </span>
        {summary.duplicate > 0 && (
          <span className="text-amber-600">
            {t('import.preview.duplicate', { count: summary.duplicate })}
          </span>
        )}
        {summary.invalid > 0 && (
          <span className="text-destructive">
            {t('import.preview.invalid', { count: summary.invalid })}
          </span>
        )}
      </div>

      {summary.duplicate > 0 && (
        <label className="flex items-center gap-x-2 text-paragraph-sm">
          <Switch blue surface checked={importDuplicates} onCheckedChange={onToggleDuplicates} />
          {t('import.preview.importDuplicates')}
        </label>
      )}

      <div className="w-full overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('import.preview.row')}</TableHead>
              {fields.map((field) => (
                <TableHead key={field.key}>{t(`import.fields.${field.key}`)}</TableHead>
              ))}
              <TableHead>{t('import.preview.status')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.rowNumber}>
                <TableCell className="text-muted-foreground">{row.rowNumber}</TableCell>
                {fields.map((field) => (
                  <TableCell key={field.key}>{row.values[field.key] ?? ''}</TableCell>
                ))}
                <TableCell>
                  <span className={cn('text-paragraph-xs-semibold', STATUS_STYLES[row.status])}>
                    {t(`import.status.${row.status}`)}
                  </span>
                  {row.errors.length > 0 && (
                    <span className="block text-paragraph-xs text-muted-foreground">
                      {row.errors.join(' ')}
                    </span>
                  )}
                  {row.warnings.length > 0 && (
                    <span className="block text-paragraph-xs text-amber-600">
                      {row.warnings.join(' ')}
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end gap-x-3">
        <Button variant="outline" onClick={onReset} disabled={confirming}>
          {t('import.preview.back')}
        </Button>
        <MotionButton
          blue
          layout
          transition={{ duration: ANIMATION_DEFAULT }}
          onClick={onConfirm}
          disabled={importable === 0 || confirming}
        >
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={confirmLabel}
              layout="position"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: ANIMATION_FAST }}
            >
              {confirmLabel}
            </motion.span>
          </AnimatePresence>
        </MotionButton>
      </div>
    </div>
  );
}
