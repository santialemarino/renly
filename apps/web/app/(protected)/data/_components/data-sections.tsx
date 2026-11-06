import { Separator } from '@repo/ui/components';
import { ExportSection } from '@/app/(protected)/data/_components/export-section';
import { ImportSection } from '@/app/(protected)/data/_components/import-section';
import { RestoreSection } from '@/app/(protected)/data/_components/restore-section';

interface DataSectionsProps {
  // The entity the import opens on (`?type=`), when a link chose one.
  initialType?: string;
}

// The data page's sections under its header — rendered by the page, and as its placeholder by its
// loading state.
export function DataSections({ initialType }: DataSectionsProps) {
  return (
    <div className="flex flex-col w-full max-w-5xl gap-y-8">
      <ImportSection initialType={initialType} />
      <Separator />
      <RestoreSection />
      <Separator />
      <ExportSection />
    </div>
  );
}
