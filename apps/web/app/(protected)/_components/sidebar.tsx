'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Settings, Table2, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';
import { ROUTES } from '@/config/routes';

const NAV_ITEMS = [
  { key: 'dashboard', href: ROUTES.dashboard, icon: LayoutDashboard },
  { key: 'investments', href: ROUTES.investments, icon: TrendingUp },
  { key: 'snapshots', href: ROUTES.snapshots, icon: Table2 },
  { key: 'settings', href: ROUTES.settings, icon: Settings },
] as const;

export function AppSidebar() {
  const pathname = usePathname();
  const t = useTranslations('sidebar');

  return (
    <Sidebar>
      <SidebarHeader className="px-4 py-5 border-b border-sidebar-border">
        <span className="text-heading-4 font-semibold text-blue-800">{t('brand')}</span>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map(({ key, href, icon: Icon }) => {
                const isActive = pathname === href || pathname.startsWith(href + '/');
                return (
                  <SidebarMenuItem key={key}>
                    <SidebarMenuButton asChild isActive={isActive}>
                      <Link href={href}>
                        <Icon />
                        <span>{t(`nav.${key}`)}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
