'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { cn } from '@repo/ui/lib';
import { ColumnMapStep } from '@/app/(protected)/data/_components/column-map-step';
import { FileStep } from '@/app/(protected)/data/_components/file-step';
import { PreviewStep } from '@/app/(protected)/data/_components/preview-step';
import { confirmImport, previewImport } from '@/app/(protected)/data/data-actions';
import { SectionHeader } from '@/components/section-header';
import type { ImportPreview } from '@/lib/api/imports';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

// The data types the engine targets. Investments ships first; the rest are upcoming specs (the
// chips advertise the general hub). Keep in sync with the backend ImportEntity enum as types land.
const DATA_TYPES = [
  { key: 'investments', enabled: true },
  { key: 'expenses', enabled: false },
  { key: 'income', enabled: false },
  { key: 'snapshots', enabled: false },
  { key: 'transactions', enabled: false },
] as const;

const ENTITY = 'investments';

export function ImportSection() {
  const t = useTranslations('data');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [importDuplicates, setImportDuplicates] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  function reset() {
    setFile(null);
    setPreview(null);
    setMapping({});
    setImportDuplicates(false);
  }

  async function runPreview(selected: File, nextMapping?: Record<string, string>) {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', selected);
    if (nextMapping) formData.append('mapping', JSON.stringify(nextMapping));
    const result = await previewImport(ENTITY, formData);
    setLoading(false);
    if ('error' in result) {
      toast.error(result.error);
      return;
    }
    setFile(selected);
    setPreview(result.data);
    setMapping(result.data.mapping);
  }

  function handleFileSelect(selected: File) {
    setImportDuplicates(false);
    runPreview(selected);
  }

  function handleMappingChange(fieldKey: string, column: string | null) {
    const next = { ...mapping };
    if (column) next[fieldKey] = column;
    else delete next[fieldKey];
    setMapping(next);
    if (file) runPreview(file, next);
  }

  async function handleConfirm() {
    if (!file) return;
    setConfirming(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mapping', JSON.stringify(mapping));
    formData.append('import_duplicates', String(importDuplicates));
    const result = await confirmImport(ENTITY, formData);
    setConfirming(false);
    if ('error' in result) {
      toast.error(result.error);
      return;
    }
    toast.success(t('import.success', { count: result.data.created }));
    reset();
  }

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('import.title')} description={t('import.description')} />

      <div className="flex flex-wrap gap-2">
        {DATA_TYPES.map((type) => (
          <span
            key={type.key}
            className={cn(
              'flex items-center px-3 py-1 gap-x-1.5 rounded-full text-paragraph-xs-medium',
              type.enabled ? 'bg-blue-800 text-white' : 'bg-muted text-muted-foreground',
            )}
          >
            {t(`types.${type.key}`)}
            {!type.enabled && <span className="text-paragraph-mini">{t('import.comingSoon')}</span>}
          </span>
        ))}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {preview ? (
          <motion.div
            key="review"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: ANIMATION_DEFAULT }}
            className="flex flex-col gap-y-6"
          >
            <ColumnMapStep preview={preview} mapping={mapping} onChange={handleMappingChange} />
            <PreviewStep
              preview={preview}
              importDuplicates={importDuplicates}
              onToggleDuplicates={setImportDuplicates}
              onConfirm={handleConfirm}
              confirming={confirming}
              onReset={reset}
            />
          </motion.div>
        ) : (
          <motion.div
            key="upload"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: ANIMATION_DEFAULT }}
          >
            <FileStep onSelect={handleFileSelect} loading={loading} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
