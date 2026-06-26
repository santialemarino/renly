'use client';

import { useRef, useState } from 'react';
import { FileUp, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';
import { InlineLink } from '@/components/inline-link';

const ACCEPT = '.csv,.tsv,.xlsx';

// Downloadable starter template per importable entity.
const DEFAULT_TEMPLATE_HREF = '/templates/investments-import-template.csv';
const TEMPLATE_HREFS: Record<string, string> = {
  investments: DEFAULT_TEMPLATE_HREF,
  expenses: '/templates/expenses-import-template.csv',
  income: '/templates/income-import-template.csv',
};

interface FileStepProps {
  entity: string;
  onSelect: (file: File) => void;
  loading: boolean;
}

export function FileStep({ entity, onSelect, loading }: FileStepProps) {
  const t = useTranslations('data');
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) onSelect(file);
  }

  return (
    <div className="flex flex-col items-start gap-y-3">
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
          // Icon tints to the buttons' blue on hover (animated both ways) — an extra hover-only cue
          // on top of the bg tint, so hover reads even more distinct from focus.
          <FileUp className="size-8 text-muted-foreground transition-colors duration-200 group-hover/dropzone:text-blue-800" />
        )}
        <span className="text-paragraph-sm-medium">
          {loading ? t('import.upload.loading') : t('import.upload.cta')}
        </span>
        <span className="text-paragraph-xs text-muted-foreground">
          {t('import.upload.formats')}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </button>

      <InlineLink
        href={TEMPLATE_HREFS[entity] ?? DEFAULT_TEMPLATE_HREF}
        color="blue"
        download
        className="text-paragraph-xs-medium"
      >
        {t('import.upload.template')}
      </InlineLink>
    </div>
  );
}
