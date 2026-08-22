'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import { LayoutGroup, motion } from 'motion/react';
import { useTranslations } from 'next-intl';

import { Button } from '@repo/ui/components';
import { GroupFormDialog } from '@/app/(protected)/shared/_components/group-form-dialog';
import { ANIMATION_DEFAULT } from '@/lib/constants/animations';

/*
 * Deliberately NOT EntityListToolbar: that component's contract is a debounced search bound to a URL
 * param, and the groups endpoint has no search — a person belongs to a handful of groups, not pages of
 * them. Rendering a search box that filters nothing would be worse than not having one.
 */
export function GroupsToolbar() {
  const t = useTranslations('shared');
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <LayoutGroup>
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        <motion.div layout transition={{ duration: ANIMATION_DEFAULT }}>
          <Button blue onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            {t('toolbar.addGroup')}
          </Button>
        </motion.div>
      </div>

      <GroupFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccess={() => router.refresh()}
      />
    </LayoutGroup>
  );
}
