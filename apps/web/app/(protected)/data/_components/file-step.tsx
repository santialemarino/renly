'use client';

import { useRef, useState } from 'react';
import { FileUp, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { cn } from '@repo/ui/lib';

const ACCEPT = '.csv,.tsv,.xlsx';
const TEMPLATE_HREF = '/templates/investments-import-template.csv';

interface FileStepProps {
  onSelect: (file: File) => void;
  loading: boolean;
}

export function FileStep({ onSelect, loading }: FileStepProps) {
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
          'flex flex-col items-center justify-center w-full p-10 gap-y-3 border-2 border-dashed rounded-xl outline-none transition-colors duration-200',
          'hover:border-blue-700 hover:bg-blue-50/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:border-ring disabled:opacity-50 disabled:pointer-events-none',
          dragging ? 'border-blue-700 bg-blue-50/40' : 'border-border',
        )}
      >
        {loading ? (
          <Loader2 className="size-8 text-muted-foreground animate-spin" />
        ) : (
          <FileUp className="size-8 text-muted-foreground" />
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

      <a
        href={TEMPLATE_HREF}
        download
        className="inline-block text-paragraph-xs-medium text-blue-700 underline decoration-transparent underline-offset-2 outline-none transition-colors duration-200 hover:decoration-blue-700 focus-visible:animate-focus-bump-subtle"
      >
        {t('import.upload.template')}
      </a>
    </div>
  );
}
