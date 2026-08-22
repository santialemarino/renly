'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Lock, Pencil, Trash2, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@repo/ui/components';
import { GroupDeleteDialog } from '@/app/(protected)/shared/_components/group-delete-dialog';
import { GroupFormDialog } from '@/app/(protected)/shared/_components/group-form-dialog';
import { RowActionButton } from '@/components/row-action-button';
import { RowLockedIndicator } from '@/components/row-locked-indicator';
import { TableEmptyRow } from '@/components/table-empty-row';
import { sharedGroupPath } from '@/config/routes';
import type { Group } from '@/lib/api/groups';

interface GroupsTableProps {
  groups: Group[];
  firstRun?: boolean;
}

export function GroupsTable({ groups, firstRun }: GroupsTableProps) {
  const t = useTranslations('shared');
  const router = useRouter();

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('table.name')}</TableHead>
          <TableHead className="w-32">{t('table.kind')}</TableHead>
          <TableHead className="w-28">{t('table.members')}</TableHead>
          <TableHead className="w-28">{t('table.yourRole')}</TableHead>
          <TableHead className="w-28 text-center">{t('table.actions')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.length === 0 ? (
          <TableEmptyRow
            colSpan={5}
            firstRun={firstRun}
            icon={Users}
            title={t('table.emptyTitle')}
            description={t('table.emptyDescription')}
            plain={t('table.empty')}
          />
        ) : (
          groups.map((group) => (
            <GroupRow key={group.id} group={group} onSuccess={() => router.refresh()} />
          ))
        )}
      </TableBody>
    </Table>
  );
}

function GroupRow({ group, onSuccess }: { group: Group; onSuccess: () => void }) {
  const t = useTranslations('shared');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const isAdmin = group.myRole === 'admin';

  return (
    <>
      <TableRow>
        <TableCell className="text-paragraph-sm-medium">{group.name}</TableCell>
        <TableCell className="text-paragraph-sm text-muted-foreground">
          {t(`kinds.${group.kind}`)}
        </TableCell>
        <TableCell className="text-paragraph-sm tabular-nums text-muted-foreground">
          {group.activeMemberCount}
        </TableCell>
        <TableCell>
          <Badge variant={isAdmin ? 'default' : 'secondary'}>{t(`roles.${group.myRole}`)}</Badge>
        </TableCell>
        <TableCell className="text-center">
          <div className="flex items-center justify-center gap-x-1">
            {/* href, not onClick: opening the hub is pure navigation, so it stays a real link and
                keeps new-tab, copy-address, middle-click and prefetch. */}
            <RowActionButton
              icon={ArrowRight}
              tooltip={t('table.openHub')}
              ariaLabel="Open group"
              href={sharedGroupPath(group.id)}
            />
            {/* Withheld rather than disabled, per the row-action convention: a Radix tooltip never
                fires on a disabled trigger, so a disabled button explains nothing. The indicator says
                where the supported action lives instead. */}
            {isAdmin ? (
              <>
                <RowActionButton
                  icon={Pencil}
                  tooltip={t('form.titleEdit')}
                  ariaLabel="Edit"
                  onClick={() => setEditOpen(true)}
                />
                <RowActionButton
                  icon={Trash2}
                  tooltip={t('delete.title')}
                  ariaLabel="Delete"
                  variant="destructive"
                  onClick={() => setDeleteOpen(true)}
                />
              </>
            ) : (
              <RowLockedIndicator
                icon={Lock}
                tooltip={t('table.memberOnly')}
                ariaLabel="Admin only"
              />
            )}
          </div>
        </TableCell>
      </TableRow>

      <GroupFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        group={group}
        onSuccess={onSuccess}
      />
      <GroupDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        group={group}
        onSuccess={onSuccess}
      />
    </>
  );
}
