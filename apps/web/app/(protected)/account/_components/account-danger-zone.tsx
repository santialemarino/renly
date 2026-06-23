'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Download, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Separator,
} from '@repo/ui/components';
import { SectionHeader } from '@/app/(protected)/account/_components/section-header';
import { deleteAccountAction, exportDataAction } from '@/app/(protected)/account/account-actions';
import { userSignOut } from '@/auth';
import { LOGIN_ROUTE } from '@/config/routes';

const EXPORT_FILENAME = 'renly-export.json';

interface AccountDangerZoneProps {
  email: string;
}

export function AccountDangerZone({ email }: AccountDangerZoneProps) {
  const t = useTranslations('account');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const [exporting, setExporting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const canDelete =
    password.length > 0 && confirmation.trim().toLowerCase() === email.toLowerCase();

  async function handleExport() {
    setExporting(true);
    try {
      const json = await exportDataAction();
      const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = EXPORT_FILENAME;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(t('danger.export.success'));
    } catch {
      toast.error(tCommon('form.errors.serverError'));
    } finally {
      setExporting(false);
    }
  }

  function handleDeleteOpenChange(open: boolean) {
    setDeleteOpen(open);
    if (!open) {
      setPassword('');
      setConfirmation('');
      setDeleteError(null);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    const result = await deleteAccountAction(password, confirmation);
    if (result.error === 'invalid_password') {
      setDeleteError(t('danger.delete.errors.invalidPassword'));
      setDeleting(false);
      return;
    }
    if (result.error) {
      setDeleteError(tCommon('form.errors.serverError'));
      setDeleting(false);
      return;
    }
    // Account is gone; clear the now-orphaned session and return to login.
    await userSignOut();
    router.push(LOGIN_ROUTE);
  }

  return (
    <section className="flex flex-col gap-y-4">
      <SectionHeader
        title={t('danger.title')}
        description={t('danger.description')}
        variant="destructive"
      />

      <div className="flex flex-col gap-y-4">
        <div className="flex items-center justify-between gap-x-4">
          <div className="flex flex-col">
            <span className="text-paragraph-sm-medium">{t('danger.export.title')}</span>
            <span className="text-paragraph-xs text-muted-foreground">
              {t('danger.export.description')}
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
            <Download className="size-4" />
            {exporting ? t('danger.export.loading') : t('danger.export.label')}
          </Button>
        </div>

        <Separator />

        <div className="flex items-center justify-between gap-x-4">
          <div className="flex flex-col">
            <span className="text-paragraph-sm-medium">{t('danger.delete.title')}</span>
            <span className="text-paragraph-xs text-muted-foreground">
              {t('danger.delete.description')}
            </span>
          </div>
          <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="size-4" />
            {t('danger.delete.label')}
          </Button>
        </div>
      </div>

      <Dialog open={deleteOpen} onOpenChange={handleDeleteOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('danger.delete.dialog.title')}</DialogTitle>
            <DialogDescription>{t('danger.delete.dialog.description')}</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-y-4">
            <div className="flex flex-col gap-y-1.5">
              <Label htmlFor="delete-password">{t('danger.delete.dialog.passwordLabel')}</Label>
              <Input
                id="delete-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                surface
                autoComplete="current-password"
                blueEye
              />
            </div>
            <div className="flex flex-col gap-y-1.5">
              <Label htmlFor="delete-confirm">
                {t('danger.delete.dialog.confirmLabel', { email })}
              </Label>
              <Input
                id="delete-confirm"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                placeholder={email}
                surface
                autoComplete="off"
              />
            </div>
            {deleteError && <p className="text-paragraph-sm text-destructive">{deleteError}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => handleDeleteOpenChange(false)}>
              {t('danger.delete.dialog.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={!canDelete || deleting}>
              {deleting ? t('danger.delete.dialog.deleting') : t('danger.delete.dialog.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
