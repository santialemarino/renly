'use client';

import { useState } from 'react';
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
import { cn } from '@repo/ui/lib';
import { createApiKey, revokeApiKey } from '@/app/(protected)/settings/settings-actions';
import { CopyButton } from '@/components/copy-button';
import type { ApiKey } from '@/lib/api/api-keys';

interface SettingsApiKeysProps {
  initialKeys: ApiKey[];
}

export function SettingsApiKeys({ initialKeys }: SettingsApiKeysProps) {
  const t = useTranslations('settings');

  const [keys, setKeys] = useState<ApiKey[]>(initialKeys);
  const [createOpen, setCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);

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
    if (!open) {
      setRawKey(null);
      setNewKeyName('');
    }
    setCreateOpen(open);
  }

  async function handleRevoke(keyId: number) {
    setRevokingId(keyId);
    try {
      await revokeApiKey(keyId);
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
      toast.success(t('apiKeys.revokeSuccess'));
    } catch {
      toast.error(t('apiKeys.revokeError'));
    } finally {
      setRevokingId(null);
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
                disabled={revokingId === key.id}
                onClick={() => handleRevoke(key.id)}
                className={cn('shrink-0', revokingId !== key.id && 'hover:text-red-500')}
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
    </div>
  );
}
