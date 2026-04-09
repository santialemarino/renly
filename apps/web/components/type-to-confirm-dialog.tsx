'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from '@repo/ui/components';

interface TypeToConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmName: string;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
  loadingLabel?: string;
  confirmLabel?: string;
  variant?: 'destructive' | 'default';
}

export function TypeToConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmName,
  onConfirm,
  loading = false,
  loadingLabel,
  confirmLabel,
  variant = 'destructive',
}: TypeToConfirmDialogProps) {
  const t = useTranslations('common');
  const [value, setValue] = useState('');

  const matches = value.trim() === confirmName.trim();

  useEffect(() => {
    if (!open) setValue('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-y-3">
          <p className="text-paragraph-sm text-muted-foreground">{description}</p>
          <div className="flex flex-col gap-y-1.5">
            <Label htmlFor="type-to-confirm">
              {t('typeToConfirm.label', { name: confirmName })}
            </Label>
            <Input
              id="type-to-confirm"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={confirmName}
              surface
              autoComplete="off"
              autoFocus
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {t('typeToConfirm.cancel')}
          </Button>
          <Button
            onClick={onConfirm}
            disabled={!matches || loading}
            variant={variant}
            className="whitespace-nowrap"
          >
            {loading
              ? (loadingLabel ?? t('typeToConfirm.loading'))
              : (confirmLabel ?? t('typeToConfirm.confirm'))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
