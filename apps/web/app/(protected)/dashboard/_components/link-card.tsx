'use client';

import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';

import { Card } from '@repo/ui/components';

interface LinkCardProps {
  href: string;
  icon: LucideIcon;
  label: string;
  hint: string;
}

export function LinkCard({ href, icon: Icon, label, hint }: LinkCardProps) {
  return (
    <Link href={href} className="group/link focus-visible:outline-none">
      <Card
        compact
        className="h-full cursor-pointer transition-colors duration-200 hover:border-blue-800/50 group-focus-visible/link:border-blue-800/50"
      >
        <Icon className="size-5 text-blue-800 group-focus-visible/link:animate-focus-bump-soft" />
        <span className="text-paragraph-sm-medium">{label}</span>
        <span className="text-paragraph-xs text-muted-foreground">{hint}</span>
      </Card>
    </Link>
  );
}
