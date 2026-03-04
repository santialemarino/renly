/** cn(): merge class names with Tailwind-aware merge (incl. custom font-size groups) */
import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

const customTwMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        'text-heading-1',
        'text-heading-2',
        'text-heading-3',
        'text-heading-4',
        'text-heading-5',
        'text-paragraph',
        'text-paragraph-medium',
        'text-paragraph-sm',
        'text-paragraph-sm-medium',
        'text-paragraph-mini',
        'text-paragraph-mini-medium',
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return customTwMerge(clsx(inputs));
}
