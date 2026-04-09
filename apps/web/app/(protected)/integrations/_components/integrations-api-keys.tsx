'use client';

import { useRef, useState } from 'react';
import { KeyRound, Plus, Trash2 } from 'lucide-react';
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
  DialogTrigger,
  Input,
  Label,
} from '@repo/ui/components';
import { createApiKey, revokeApiKey } from '@/app/(protected)/integrations/integrations-actions';
import { CopyButton } from '@/components/copy-button';
import { TypeToConfirmDialog } from '@/components/type-to-confirm-dialog';
import type { ApiKey } from '@/lib/api/api-keys';

interface IntegrationsApiKeysProps {
  initialKeys: ApiKey[];
}

export function IntegrationsApiKeys({ initialKeys }: IntegrationsApiKeysProps) {
  const t = useTranslations('integrations');

  const [keys, setKeys] = useState<ApiKey[]>(initialKeys);
  const [createOpen, setCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [revokeKey, setRevokeKey] = useState<ApiKey | null>(null);
  const [revoking, setRevoking] = useState(false);

  // Preserve revoke key data during close animation.
  const lastRevokeKey = useRef(revokeKey);
  if (revokeKey) lastRevokeKey.current = revokeKey;
  const displayRevokeKey = revokeKey ?? lastRevokeKey.current;

  async function handleCreate() {
    setCreating(true);
    try {
      const result = await createApiKey(newKeyName || null);
      setRawKey(result.rawKey);
      setKeys((prev) => [
        {
          id: result.id,
          name: result.name,
          createdAt: new Date().toISOString(),
          lastUsedAt: null,
          isActive: true,
        },
        ...prev,
      ]);
      toast.success(t('apiKeys.createSuccess'));
    } catch {
      toast.error(t('apiKeys.createError'));
      setCreateOpen(false);
    } finally {
      setCreating(false);
    }
  }

  function handleDialogClose(open: boolean) {
    setCreateOpen(open);
    if (!open) {
      // Delay state reset so dialog content stays visible during close animation.
      setTimeout(() => {
        setRawKey(null);
        setNewKeyName('');
      }, 200);
    }
  }

  async function handleRevoke() {
    if (!revokeKey) return;
    setRevoking(true);
    try {
      await revokeApiKey(revokeKey.id);
      setKeys((prev) => prev.filter((k) => k.id !== revokeKey.id));
      toast.success(t('apiKeys.revokeSuccess'));
      setRevokeKey(null);
    } catch {
      toast.error(t('apiKeys.revokeError'));
    } finally {
      setRevoking(false);
    }
  }

  // Formats a timestamp as a short date string.
  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  return (
    <div className="flex flex-col w-full max-w-2xl gap-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-y-1">
          <h3 className="text-paragraph-sm-semibold text-muted-foreground">{t('apiKeys.title')}</h3>
          <p className="text-paragraph-xs text-muted-foreground">{t('apiKeys.description')}</p>
        </div>

        <Dialog open={createOpen} onOpenChange={handleDialogClose}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Plus className="size-4" />
              {t('apiKeys.create')}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {rawKey ? t('apiKeys.dialog.titleCreated') : t('apiKeys.dialog.titleCreate')}
              </DialogTitle>
              <DialogDescription>
                {rawKey
                  ? t('apiKeys.dialog.descriptionCreated')
                  : t('apiKeys.dialog.descriptionCreate')}
              </DialogDescription>
            </DialogHeader>

            {rawKey ? (
              <div className="flex flex-col gap-y-3">
                <Label>{t('apiKeys.dialog.keyLabel')}</Label>
                <div className="flex items-center gap-x-2">
                  <Input value={rawKey} readOnly surface className="font-mono text-paragraph-xs" />
                  <CopyButton value={rawKey} />
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-y-2">
                <Label>{t('apiKeys.dialog.nameLabel')}</Label>
                <Input
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder={t('apiKeys.dialog.namePlaceholder')}
                  surface
                  maxLength={100}
                />
              </div>
            )}

            <DialogFooter>
              {rawKey ? (
                <Button blue onClick={() => handleDialogClose(false)}>
                  {t('apiKeys.dialog.done')}
                </Button>
              ) : (
                <Button blue onClick={handleCreate} disabled={creating}>
                  {creating ? t('apiKeys.dialog.creating') : t('apiKeys.dialog.create')}
                </Button>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {keys.length > 0 ? (
        <div className="flex flex-col gap-y-2">
          {keys.map((key) => (
            <div
              key={key.id}
              className="flex items-center justify-between p-3 gap-x-4 border rounded-lg"
            >
              <div className="flex items-center gap-x-3">
                <KeyRound className="size-4 shrink-0 text-muted-foreground" />
                <div className="flex flex-col">
                  <span className="text-paragraph-sm-medium">
                    {key.name || t('apiKeys.unnamed')}
                  </span>
                  <span className="text-paragraph-xs text-muted-foreground">
                    {t('apiKeys.created', { date: formatDate(key.createdAt) })}
                    {key.lastUsedAt &&
                      ` · ${t('apiKeys.lastUsed', { date: formatDate(key.lastUsedAt) })}`}
                  </span>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setRevokeKey(key)}
                className="shrink-0 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center justify-center p-6 border border-dashed rounded-lg">
          <p className="text-paragraph-sm text-muted-foreground">{t('apiKeys.empty')}</p>
        </div>
      )}

      <TypeToConfirmDialog
        open={!!revokeKey}
        onOpenChange={(open) => {
          if (!open) setRevokeKey(null);
        }}
        title={t('apiKeys.revoke.title')}
        description={t('apiKeys.revoke.description', {
          name: displayRevokeKey?.name || t('apiKeys.unnamed'),
        })}
        confirmName={displayRevokeKey?.name || t('apiKeys.unnamed')}
        onConfirm={handleRevoke}
        loading={revoking}
        loadingLabel={t('apiKeys.revoke.revoking')}
        confirmLabel={t('apiKeys.revoke.confirm')}
      />
    </div>
  );
}
