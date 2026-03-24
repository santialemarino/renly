'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { FolderOpen, LayoutDashboard, LogOut, Settings, Table2, TrendingUp } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Separator,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { CurrencySwitcher } from '@/app/(protected)/_components/currency-switcher';
import { userSignOut } from '@/auth';
import { LOGIN_ROUTE, ROUTES } from '@/config/routes';

const NAV_ITEMS = [
  { key: 'dashboard', href: ROUTES.dashboard, icon: LayoutDashboard },
  { key: 'investments', href: ROUTES.investments, icon: TrendingUp },
  { key: 'groups', href: ROUTES.groups, icon: FolderOpen },
  { key: 'snapshots', href: ROUTES.snapshots, icon: Table2 },
  { key: 'settings', href: ROUTES.settings, icon: Settings },
] as const;

interface AppSidebarProps {
  displayCurrencies: string[];
  activeCurrency: string;
}

export function AppSidebar({ displayCurrencies, activeCurrency }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations('sidebar');
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    await userSignOut();
    router.push(LOGIN_ROUTE);
  }

  return (
    <Sidebar className="border-sidebar-border shadow-lg">
      <SidebarHeader className="pl-4 py-5 border-b border-sidebar-border">
        <span className="text-heading-2 text-blue-800">{t('brand')}</span>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="p-4">
          <SidebarGroupContent>
            <SidebarMenu className="gap-y-2">
              {NAV_ITEMS.map(({ key, href, icon: Icon }) => {
                const isActive = pathname === href || pathname.startsWith(href + '/');
                return (
                  <SidebarMenuItem key={key}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      size="lg"
                      className={cn(
                        'text-paragraph-medium hover:bg-gray-100 data-[active=true]:bg-blue-800 data-[active=true]:text-white [&_svg]:size-5',
                        !isActive && 'hover:[&_svg]:rotate-12',
                      )}
                    >
                      <Link className="gap-x-2" href={href}>
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

        <Separator />

        <SidebarGroup className="p-4">
          <SidebarGroupContent>
            <CurrencySwitcher
              key={displayCurrencies.join(',')}
              displayCurrencies={displayCurrencies}
              activeCurrency={activeCurrency}
            />
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={handleLogout}
              disabled={loggingOut}
              size="lg"
              className={cn(
                'text-paragraph-medium hover:text-red-500 hover:bg-transparent active:bg-transparent [&_svg]:size-5',
                loggingOut && 'text-red-800 hover:text-red-800',
              )}
            >
              <LogOut />
              <span>{loggingOut ? t('logout.loading') : t('logout.label')}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
