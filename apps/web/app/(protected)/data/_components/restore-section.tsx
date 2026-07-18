'use client';

import { useRef, useState } from 'react';
import { Loader2, RotateCcw } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
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
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { confirmRestore, previewRestore } from '@/app/(protected)/data/data-actions';
import { SectionHeader } from '@/components/section-header';
import type { RestorePreview } from '@/lib/api/restore';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';
import { useFormatters } from '@/lib/i18n/formatters';

export function RestoreSection() {
  const fmt = useFormatters();
  const t = useTranslations('data');
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<RestorePreview | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  function reset() {
    setFile(null);
    setPreview(null);
  }

  async function runPreview(selected: File) {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', selected);
    const result = await previewRestore(formData);
    setLoading(false);
    if ('error' in result) {
      toast.error(result.error);
      return;
    }
    setFile(selected);
    setPreview(result.data);
  }

  function handleFiles(files: FileList | null) {
    const selected = files?.[0];
    if (selected) runPreview(selected);
  }

  async function handleConfirm() {
    if (!file) return;
    setConfirming(true);
    const formData = new FormData();
    formData.append('file', file);
    const result = await confirmRestore(formData);
    setConfirming(false);
    if ('error' in result) {
      toast.error(result.error);
      return;
    }
    toast.success(t('restore.success', { count: result.data.restored }));
    reset();
  }

  // Rows worth showing: an entity that has something to restore or something skipped.
  const shownEntities =
    preview?.entities.filter((entity) => entity.restore + entity.skippedUnresolved > 0) ?? [];
  const totalToRestore = preview?.entities.reduce((sum, entity) => sum + entity.restore, 0) ?? 0;

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('restore.title')} description={t('restore.description')} />

      <AnimatePresence mode="wait" initial={false}>
        {preview ? (
          <motion.div
            key="review"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: ANIMATION_DEFAULT }}
            className="flex flex-col gap-y-4"
          >
            <span className="text-paragraph-sm">
              {t('restore.summary', { count: totalToRestore })}
            </span>

            <div className="w-full overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('restore.table.entity')}</TableHead>
                    <TableHead>{t('restore.table.toRestore')}</TableHead>
                    <TableHead>{t('restore.table.skipped')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shownEntities.map((entity) => (
                    <TableRow key={entity.entity}>
                      <TableCell>{t(`restore.entities.${entity.entity}`)}</TableCell>
                      <TableCell className={cn(entity.restore > 0 && 'text-green-700')}>
                        {entity.restore}
                      </TableCell>
                      <TableCell className={cn(entity.skippedUnresolved > 0 && 'text-amber-600')}>
                        {entity.skippedUnresolved}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {preview.skippedEntities.length > 0 && (
              <span className="text-paragraph-xs text-muted-foreground">
                {t('restore.notRestored', {
                  entities: fmt.list(
                    preview.skippedEntities.map((entity) => t(`restore.entities.${entity}`)),
                  ),
                })}
              </span>
            )}

            <div className="flex items-center justify-end gap-x-3">
              <Button variant="outline" onClick={reset} disabled={confirming}>
                {t('restore.back')}
              </Button>
              <Button blue onClick={handleConfirm} disabled={totalToRestore === 0 || confirming}>
                {confirming
                  ? t('restore.restoring')
                  : t('restore.confirm', { count: totalToRestore })}
              </Button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="upload"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: ANIMATION_DEFAULT }}
            className="flex flex-col items-start gap-y-3"
          >
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                handleFiles(e.dataTransfer.files);
              }}
              disabled={loading}
              className={cn(
                'group/dropzone flex flex-col items-center justify-center w-full p-10 gap-y-3 border-2 border-dashed rounded-xl outline-none transition-colors duration-200',
                // Focus-visible mirrors hover's blue border but without the bg tint (and no ring), so the
                // keyboard cue is clearly present yet distinct from the hover state.
                'hover:border-blue-700 hover:bg-blue-50/40 focus-visible:border-blue-700 disabled:opacity-50 disabled:pointer-events-none',
                dragging ? 'border-blue-700 bg-blue-50/40' : 'border-border',
              )}
            >
              {loading ? (
                <Loader2 className="size-8 text-muted-foreground animate-spin" />
              ) : (
                <RotateCcw className="size-8 text-muted-foreground transition-colors duration-200 group-hover/dropzone:text-blue-800" />
              )}
              <span className="text-paragraph-sm-medium">
                {loading ? t('restore.upload.loading') : t('restore.upload.cta')}
              </span>
              <span className="text-paragraph-xs text-muted-foreground">
                {t('restore.upload.hint')}
              </span>
              <input
                ref={inputRef}
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
