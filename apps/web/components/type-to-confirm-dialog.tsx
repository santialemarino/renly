'use client';

import { useEffect, useRef, useState } from 'react';
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
} from '@repo/ui/components';

interface TypeToConfirmDialogProps<TEntity> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Entity being confirmed. May go null while the close animation plays — the last
  // non-null value is retained internally so the copy doesn't blank out mid-exit.
  entity: TEntity | null;
  title: string;
  description: (entity: TEntity) => string;
  confirmName: (entity: TEntity) => string;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
  loadingLabel?: string;
  confirmLabel?: string;
  variant?: 'destructive' | 'default';
}

export function TypeToConfirmDialog<TEntity>({
  open,
  onOpenChange,
  entity,
  title,
  description,
  confirmName,
  onConfirm,
  loading = false,
  loadingLabel,
  confirmLabel,
  variant = 'destructive',
}: TypeToConfirmDialogProps<TEntity>) {
  const t = useTranslations('common');
  const [value, setValue] = useState('');

  // Preserve the entity during the close animation so the copy doesn't disappear mid-exit.
  const lastEntity = useRef(entity);
  if (entity) lastEntity.current = entity;
  const display = entity ?? lastEntity.current;

  const name = display ? confirmName(display) : '';
  const matches = value.trim() === name.trim();

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
          {/* DialogDescription via asChild: Radix needs it to wire aria-describedby (and warns
              "Missing `Description` or `aria-describedby={undefined}`" without it), while asChild keeps
              this paragraph's own styling instead of adopting the primitive's flex + text-sm. */}
          <DialogDescription asChild>
            <p className="text-paragraph-sm text-muted-foreground">
              {display ? description(display) : ''}
            </p>
          </DialogDescription>
          <div className="flex flex-col gap-y-1.5">
            <Label htmlFor="type-to-confirm">{t('typeToConfirm.label', { name })}</Label>
            <Input
              id="type-to-confirm"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={name}
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
