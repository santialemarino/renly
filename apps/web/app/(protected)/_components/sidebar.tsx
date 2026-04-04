'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  ChevronRight,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  Rows3,
  Settings,
  Table2,
  TrendingUp,
} from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
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
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { CurrencySwitcher } from '@/app/(protected)/_components/currency-switcher';
import { userSignOut } from '@/auth';
import { LOGIN_ROUTE, ROUTES } from '@/config/routes';

const PORTFOLIO_GROUP = [
  { key: 'dashboard', href: ROUTES.dashboard, icon: LayoutDashboard },
  { key: 'investments', href: ROUTES.investments, icon: Rows3 },
  { key: 'groups', href: ROUTES.groups, icon: FolderOpen },
  { key: 'snapshots', href: ROUTES.snapshots, icon: Table2 },
] as const;

/** Shared interactive states for all nav items (main buttons and sub-buttons). */
const NAV_ITEM_STYLES =
  'hover:bg-gray-100 active:bg-gray-200 focus-visible:bg-gray-100 focus-visible:outline-none focus-visible:ring-0 data-[active=true]:bg-blue-800 data-[active=true]:text-white data-[active=true]:hover:bg-blue-900 data-[active=true]:active:bg-blue-950 data-[active=true]:focus-visible:bg-blue-900';

/** Extra styles for SidebarMenuSubButton: transition (not baked in) and svg icon animation. */
const SUB_BUTTON_EXTRAS =
  'transition-[background-color,color] duration-200 ease-out [&_svg]:transition-transform [&_svg]:duration-200 [&_svg]:ease-out';

interface AppSidebarProps {
  displayCurrencies: string[];
  activeCurrency: string;
}

export function AppSidebar({ displayCurrencies, activeCurrency }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations('sidebar');
  const [loggingOut, setLoggingOut] = useState(false);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + '/');
  const isGroupActive = PORTFOLIO_GROUP.some(({ href }) => isActive(href));

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
              {/* Portfolio collapsible group */}
              <Collapsible asChild defaultOpen={isGroupActive} className="group/collapsible">
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      size="lg"
                      className={cn(
                        '[&_svg]:size-5 text-paragraph-medium',
                        NAV_ITEM_STYLES,
                        'data-[active=true]:bg-transparent data-[active=true]:text-current',
                      )}
                    >
                      <TrendingUp />
                      <span>{t('navGroups.portfolio')}</span>
                      <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
                    <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                      {PORTFOLIO_GROUP.map(({ key, href, icon: Icon }) => {
                        const active = isActive(href);
                        return (
                          <SidebarMenuSubItem key={key}>
                            <SidebarMenuSubButton
                              asChild
                              isActive={active}
                              className={cn(
                                'h-8 text-paragraph-sm-medium',
                                NAV_ITEM_STYLES,
                                SUB_BUTTON_EXTRAS,
                                !active &&
                                  'hover:[&_svg]:rotate-12 focus-visible:[&_svg]:rotate-12',
                              )}
                            >
                              <Link href={href}>
                                <Icon />
                                <span>{t(`nav.${key}`)}</span>
                              </Link>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        );
                      })}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

              {/* Settings */}
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={isActive(ROUTES.settings)}
                  size="lg"
                  className={cn(
                    '[&_svg]:size-5 text-paragraph-medium',
                    NAV_ITEM_STYLES,
                    !isActive(ROUTES.settings) &&
                      'hover:[&_svg]:rotate-12 focus-visible:[&_svg]:rotate-12',
                  )}
                >
                  <Link className="gap-x-2" href={ROUTES.settings}>
                    <Settings />
                    <span>{t('nav.settings')}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
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
                'text-paragraph-medium hover:text-red-500 hover:bg-transparent focus-visible:text-red-500 focus-visible:bg-transparent focus-visible:outline-none focus-visible:ring-0 active:bg-transparent [&_svg]:size-5',
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
