'use client';

import { useState } from 'react';
import { Check } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Button,
  Command,
  CommandGroup,
  CommandItem,
  CommandList,
  Label,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { ComboboxChevron } from '@/components/combobox-chevron';
import type { ImportPreview } from '@/lib/api/imports';

interface ColumnMapStepProps {
  preview: ImportPreview;
  mapping: Record<string, string>;
  onChange: (fieldKey: string, column: string | null) => void;
}

export function ColumnMapStep({ preview, mapping, onChange }: ColumnMapStepProps) {
  const t = useTranslations('data');

  return (
    <div className="flex flex-col gap-y-3">
      <span className="text-paragraph-sm-medium">{t('import.map.title')}</span>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {preview.fields.map((field) => (
          <div key={field.key} className="flex flex-col gap-y-1.5">
            <Label required={field.required} className="text-paragraph-xs-medium">
              {t(`import.fields.${field.key}`)}
            </Label>
            <FieldMapCombobox
              value={mapping[field.key] ?? null}
              columns={preview.columns}
              ignoreLabel={t('import.map.ignore')}
              onChange={(column) => onChange(field.key, column)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

interface FieldMapComboboxProps {
  value: string | null;
  columns: string[];
  ignoreLabel: string;
  onChange: (column: string | null) => void;
}

// Popover + Command combobox (the app's standalone-selector pattern) so the dropdown animates on
// both open and close — Radix Select does not animate close. The chevron rotates on open.
function FieldMapCombobox({ value, columns, ignoreLabel, onChange }: FieldMapComboboxProps) {
  const [open, setOpen] = useState(false);

  function handleSelect(column: string | null) {
    onChange(column);
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          className="h-9 w-full justify-between px-3 gap-x-2 bg-background text-paragraph-sm font-normal hover:border-ring focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <span className={cn('truncate', !value && 'text-muted-foreground')}>
            {value ?? ignoreLabel}
          </span>
          <ComboboxChevron open={open} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
        <Command>
          <CommandList>
            <CommandGroup>
              <CommandItem value={ignoreLabel} onSelect={() => handleSelect(null)}>
                <Check
                  className={cn(
                    'size-4 shrink-0 transition-all duration-150',
                    !value ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                  )}
                />
                {ignoreLabel}
              </CommandItem>
              {columns.map((column) => (
                <CommandItem key={column} value={column} onSelect={() => handleSelect(column)}>
                  <Check
                    className={cn(
                      'size-4 shrink-0 transition-all duration-150',
                      value === column ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                    )}
                  />
                  {column}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
