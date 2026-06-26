'use client';

import { useState, type ComponentProps } from 'react';
import { Download } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@repo/ui/components';
import { exportData } from '@/app/(protected)/data/data-actions';

const EXPORT_FILENAME = 'renly-export.json';

interface ExportDataButtonProps {
  variant?: ComponentProps<typeof Button>['variant'];
  className?: string;
}

// Downloads the user's full data export (AUTH-6) as a JSON file. Shared by the Data page and the
// account delete dialog (export-before-you-leave), so the export action lives in one place.
export function ExportDataButton({ variant = 'outline', className }: ExportDataButtonProps) {
  const t = useTranslations('data');
  const tCommon = useTranslations('common');
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const json = await exportData();
      const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = EXPORT_FILENAME;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(t('export.success'));
    } catch {
      toast.error(tCommon('form.errors.serverError'));
    } finally {
      setExporting(false);
    }
  }

  return (
    <Button
      variant={variant}
      size="sm"
      onClick={handleExport}
      disabled={exporting}
      className={className}
    >
      <Download className="size-4" />
      {exporting ? t('export.loading') : t('export.label')}
    </Button>
  );
}
