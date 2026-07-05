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

// The data types the engine targets. Enabled types are selectable; the rest are upcoming specs
// (their chips advertise the general hub). Keep in sync with the backend ImportEntity enum.
const DATA_TYPES = [
  { key: 'investments', enabled: true },
  { key: 'expenses', enabled: true },
  { key: 'income', enabled: true },
  { key: 'snapshots', enabled: true },
  { key: 'transactions', enabled: true },
] as const;

type DataTypeKey = (typeof DATA_TYPES)[number]['key'];

const DEFAULT_ENTITY: DataTypeKey = 'investments';

// Resolves the entity to start on: an enabled type named by the `?type=` deep-link, else the default.
function resolveInitialEntity(initialType?: string): DataTypeKey {
  return DATA_TYPES.find((type) => type.enabled && type.key === initialType)?.key ?? DEFAULT_ENTITY;
}

interface ImportSectionProps {
  initialType?: string;
}

export function ImportSection({ initialType }: ImportSectionProps) {
  const t = useTranslations('data');
  const [entity, setEntity] = useState<DataTypeKey>(() => resolveInitialEntity(initialType));
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

  // Switching the active data type restarts the wizard (mapping and preview are entity-specific).
  function handleSelectType(key: DataTypeKey) {
    if (key === entity) return;
    setEntity(key);
    reset();
  }

  async function runPreview(selected: File, nextMapping?: Record<string, string>) {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', selected);
    if (nextMapping) formData.append('mapping', JSON.stringify(nextMapping));
    const result = await previewImport(entity, formData);
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
    const result = await confirmImport(entity, formData);
    setConfirming(false);
    if ('error' in result) {
      toast.error(result.error);
      return;
    }
    toast.success(t('import.success', { count: result.data.created, entity }));
    reset();
  }

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader title={t('import.title')} description={t('import.description')} />

      <div className="flex flex-wrap gap-2" role="group" aria-label={t('import.typeLabel')}>
        {DATA_TYPES.map((type) =>
          type.enabled ? (
            <button
              key={type.key}
              type="button"
              onClick={() => handleSelectType(type.key)}
              aria-pressed={entity === type.key}
              // Lock the picker while a preview/confirm is in flight: switching entities mid-request
              // would let a stale result render under the newly selected type.
              disabled={loading || confirming}
              className={cn(
                'flex items-center px-3 py-1 rounded-full outline-none transition-all duration-200 cursor-pointer',
                'active:scale-95 focus-visible:ring-3 disabled:opacity-50 disabled:pointer-events-none text-paragraph-xs-medium',
                // Focus ring tint matches the button variants: blue (active) ring like a blue
                // button, neutral ring for the muted (inactive) tabs — so the active tab's keyboard
                // focus reads distinct from the others.
                entity === type.key
                  ? 'bg-blue-800 text-white focus-visible:ring-blue-800/50'
                  : 'bg-muted text-foreground hover:bg-muted/70 focus-visible:ring-ring/50',
              )}
            >
              {t(`types.${type.key}`)}
            </button>
          ) : (
            <span
              key={type.key}
              className="flex items-center px-3 py-1 gap-x-1.5 rounded-full bg-muted text-muted-foreground text-paragraph-xs-medium"
            >
              {t(`types.${type.key}`)}
              <span className="text-paragraph-mini">{t('import.comingSoon')}</span>
            </span>
          ),
        )}
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
              entity={entity}
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
            <FileStep entity={entity} onSelect={handleFileSelect} loading={loading} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
