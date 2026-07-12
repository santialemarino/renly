'use client';

import { useRef } from 'react';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@repo/ui/components';

interface ConfirmDialogProps<TEntity> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Entity being confirmed. May go null while the close animation plays — the last
  // non-null value is retained internally so the copy doesn't blank out mid-exit.
  entity: TEntity | null;
  title: string;
  description: (entity: TEntity) => string;
  onConfirm: () => void | Promise<void>;
  loading?: boolean;
  loadingLabel: string;
  confirmLabel: string;
  cancelLabel: string;
}

// Plain destructive confirmation dialog (no type-to-confirm input).
export function ConfirmDialog<TEntity>({
  open,
  onOpenChange,
  entity,
  title,
  description,
  onConfirm,
  loading = false,
  loadingLabel,
  confirmLabel,
  cancelLabel,
}: ConfirmDialogProps<TEntity>) {
  // Preserve the entity during the close animation so the copy doesn't blank out mid-exit.
  const lastEntity = useRef(entity);
  if (entity) lastEntity.current = entity;
  const display = entity ?? lastEntity.current;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{display ? description(display) : ''}</DialogDescription>
        <DialogFooter>
          <Button
            variant="outline"
            className="whitespace-nowrap"
            onClick={() => onOpenChange(false)}
          >
            {cancelLabel}
          </Button>
          <Button
            onClick={onConfirm}
            disabled={loading}
            variant="destructive"
            className="whitespace-nowrap"
          >
            {loading ? loadingLabel : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
