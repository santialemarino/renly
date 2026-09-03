'use client';

import type { LucideIcon } from 'lucide-react';

import { Pill } from '@repo/ui/components';

interface SegmentedPillsProps<T extends string> {
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
  // Accessible name for the group, since the individual pills only carry their own words.
  label: string;
  labelFor: (option: T) => string;
  iconFor?: (option: T) => LucideIcon | undefined;
}

/*
 * A small segmented control: one `Pill` per value inside a bordered group, exactly one of them active.
 *
 * ONE component because a list-page toolbar now carries two of these — the scope filter and the
 * snapshots grid's column interval — and two copies of the same control are two things that stop
 * looking alike. Built on `Pill` rather than `ToggleGroup` so it matches the archived pill it sits
 * beside, with `animate-pulse-scale` for the press-in feedback the motion convention gives a
 * segmented control.
 *
 * Every one of these FILTERS, and none of them is a mode: the selection lives in the URL, where it is
 * visible and gone on the next visit, rather than in remembered state that could quietly narrow a page
 * somebody then misreads as the whole.
 */
export function SegmentedPills<T extends string>({
  value,
  options,
  onChange,
  label,
  labelFor,
  iconFor,
}: SegmentedPillsProps<T>) {
  return (
    <div
      className="flex min-w-fit items-center p-0.5 bg-background border border-border rounded-md shadow-xs"
      role="group"
      aria-label={label}
    >
      {options.map((option) => {
        const active = value === option;
        const Icon = iconFor?.(option);
        return (
          <Pill
            key={option}
            active={active}
            aria-pressed={active}
            onClick={() => onChange(option)}
            className="h-8 px-2.5 border-0 shadow-none active:animate-pulse-scale text-paragraph-sm"
          >
            {Icon && <Icon className="size-3.5" />}
            {labelFor(option)}
          </Pill>
        );
      })}
    </div>
  );
}
