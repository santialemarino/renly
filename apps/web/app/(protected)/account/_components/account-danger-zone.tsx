'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

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
import { deleteAccountAction } from '@/app/(protected)/account/account-actions';
import { userSignOut } from '@/auth';
import { ExportDataButton } from '@/components/export-data-button';
import { SectionHeader } from '@/components/section-header';
import { LOGIN_ROUTE } from '@/config/routes';

interface AccountDangerZoneProps {
  email: string;
}

export function AccountDangerZone({ email }: AccountDangerZoneProps) {
  const t = useTranslations('account');
  const tCommon = useTranslations('common');
  const router = useRouter();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const canDelete =
    password.length > 0 && confirmation.trim().toLowerCase() === email.toLowerCase();

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

      <Dialog open={deleteOpen} onOpenChange={handleDeleteOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('danger.delete.dialog.title')}</DialogTitle>
            <DialogDescription>{t('danger.delete.dialog.description')}</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-y-4">
            {/* Export-before-you-leave: grab a copy without leaving the deletion flow. */}
            <div className="flex items-center justify-between gap-x-4">
              <span className="text-paragraph-sm text-muted-foreground">
                {t('danger.exportFirst.text')}
              </span>
              <ExportDataButton />
            </div>
            <Separator />
            <div className="flex flex-col gap-y-1.5">
              <Label htmlFor="delete-password">{t('danger.delete.dialog.passwordLabel')}</Label>
              <Input
                id="delete-password"
                type="password"
                passwordToggleLabel={tCommon('form.togglePassword')}
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
