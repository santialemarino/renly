'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  BarChart3,
  Bell,
  CalendarClock,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  CreditCard,
  FileText,
  FolderOpen,
  Globe,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Puzzle,
  Receipt,
  RefreshCw,
  Rows3,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Table2,
  TrendingUp,
  UserCog,
  UserPlus,
  Wallet,
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
import { Brand } from '@/components/brand';
import { TruncatingTooltip } from '@/components/truncating-tooltip';
import { LOGIN_ROUTE, ROUTES } from '@/config/routes';
import type { SignupMode } from '@/lib/auth-api';

const FINANCES_GROUP = [
  { key: 'financeDashboard', href: ROUTES.financeDashboard, icon: BarChart3 },
  { key: 'income', href: ROUTES.income, icon: CircleDollarSign },
  { key: 'expenses', href: ROUTES.expenses, icon: Receipt },
  { key: 'creditCards', href: ROUTES.creditCards, icon: CreditCard },
] as const;

const COMMITMENTS_GROUP = [
  { key: 'subscriptions', href: ROUTES.subscriptions, icon: RefreshCw },
  { key: 'installments', href: ROUTES.installments, icon: ListChecks },
  { key: 'paymentObligations', href: ROUTES.paymentObligations, icon: FileText },
  { key: 'paymentsCalendar', href: ROUTES.paymentsCalendar, icon: CalendarClock },
] as const;

const PORTFOLIO_GROUP = [
  { key: 'investorDashboard', href: ROUTES.investorDashboard, icon: BarChart3 },
  { key: 'investments', href: ROUTES.investments, icon: Rows3 },
  { key: 'groups', href: ROUTES.groups, icon: FolderOpen },
  { key: 'snapshots', href: ROUTES.snapshots, icon: Table2 },
] as const;

const SETTINGS_GROUP = [
  { key: 'account', href: ROUTES.account, icon: UserCog },
  { key: 'preferences', href: ROUTES.preferences, icon: SlidersHorizontal },
  { key: 'alerts', href: ROUTES.alerts, icon: Bell },
  { key: 'localization', href: ROUTES.localization, icon: Globe },
  { key: 'integrations', href: ROUTES.integrations, icon: Puzzle },
] as const;

// Admin-only group (rendered only when the user is an admin). Items can be gated further:
// invitePeople is only relevant in invite mode (in open mode anyone signs up, so there's no one to invite).
const ADMIN_GROUP = [
  { key: 'invitePeople', href: ROUTES.admin, icon: UserPlus, inviteOnly: true },
] as const;

/** Shared interactive states for all nav items (main buttons and sub-buttons). */
const NAV_ITEM_STYLES =
  'hover:bg-gray-100 active:bg-gray-200 focus-visible:bg-gray-100 focus-visible:outline-none focus-visible:ring-0 data-[active=true]:bg-blue-800 data-[active=true]:text-white data-[active=true]:hover:bg-blue-900 data-[active=true]:active:bg-blue-950 data-[active=true]:focus-visible:bg-blue-900';

/** Extra styles for SidebarMenuSubButton: hover text color (matching the main button primitive), transition, and svg icon animation. */
const SUB_BUTTON_EXTRAS =
  'hover:text-sidebar-accent-foreground focus-visible:text-sidebar-accent-foreground transition-[background-color,color] duration-200 ease-out [&_svg]:transition-transform [&_svg]:duration-200 [&_svg]:ease-out';

interface AppSidebarProps {
  displayCurrencies: string[];
  activeCurrency: string;
  currencyCollapsed: boolean;
  isAdmin: boolean;
  signupMode: SignupMode;
}

export function AppSidebar({
  displayCurrencies,
  activeCurrency,
  currencyCollapsed,
  isAdmin,
  signupMode,
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations('sidebar');
  const [loggingOut, setLoggingOut] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + '/');
  const isCommitmentsActive = COMMITMENTS_GROUP.some(({ href }) => isActive(href));
  // Finances "section" is active when any direct child or any nested Commitments child is active.
  const isFinancesActive = FINANCES_GROUP.some(({ href }) => isActive(href)) || isCommitmentsActive;
  const isPortfolioActive = PORTFOLIO_GROUP.some(({ href }) => isActive(href));
  const isSettingsActive = SETTINGS_GROUP.some(({ href }) => isActive(href));

  // Admin group: only for admins, and only items whose gate matches (invitePeople → invite mode).
  // When no item qualifies (e.g. open mode), the whole group is hidden.
  const adminItems = ADMIN_GROUP.filter((item) => !item.inviteOnly || signupMode === 'invite');
  const showAdminGroup = isAdmin && adminItems.length > 0;
  const isAdminActive = adminItems.some(({ href }) => isActive(href));

  // Suppress collapsible animation on first render so open groups don't animate in.
  const collapsibleContentClass = mounted
    ? 'overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up'
    : 'overflow-hidden';

  async function handleLogout() {
    setLoggingOut(true);
    await userSignOut();
    router.push(LOGIN_ROUTE);
  }

  return (
    <Sidebar className="border-sidebar-border shadow-lg">
      <SidebarHeader className="pl-4 py-5 border-b border-sidebar-border">
        <Brand name={t('brand')} size="lg" />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="p-4">
          <SidebarGroupContent>
            <SidebarMenu className="gap-y-2">
              {/* General Dashboard — top-level, not inside any group */}
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={isActive(ROUTES.dashboard)}
                  size="lg"
                  className={cn(
                    '[&_svg]:size-5 text-paragraph-medium',
                    NAV_ITEM_STYLES,
                    !isActive(ROUTES.dashboard) &&
                      'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                  )}
                >
                  <Link href={ROUTES.dashboard}>
                    <LayoutDashboard />
                    <span>{t('nav.dashboard')}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {/* Finances collapsible group */}
              <Collapsible asChild defaultOpen={isFinancesActive} className="group/collapsible">
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      size="lg"
                      className={cn(
                        '[&_svg]:size-5 text-paragraph-medium',
                        NAV_ITEM_STYLES,
                        !isFinancesActive &&
                          'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                        isFinancesActive && 'bg-gray-100',
                      )}
                    >
                      <Wallet />
                      <span>{t('navGroups.finances')}</span>
                      <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent className={collapsibleContentClass}>
                    <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                      {FINANCES_GROUP.map(({ key, href, icon: Icon }) => {
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
                                <TruncatingTooltip text={t(`nav.${key}`)} side="right" />
                              </Link>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        );
                      })}

                      {/* Nested Commitments subgroup — subscriptions, installments, obligations, calendar. */}
                      <Collapsible
                        asChild
                        defaultOpen={isCommitmentsActive}
                        className="group/inner-collapsible"
                      >
                        <SidebarMenuSubItem>
                          <CollapsibleTrigger asChild>
                            <SidebarMenuSubButton
                              className={cn(
                                'h-8 text-paragraph-sm-medium cursor-pointer',
                                NAV_ITEM_STYLES,
                                SUB_BUTTON_EXTRAS,
                                isCommitmentsActive && 'bg-gray-100',
                                !isCommitmentsActive &&
                                  'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                              )}
                            >
                              <ClipboardList />
                              <span>{t('navGroups.commitments')}</span>
                              <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/inner-collapsible:rotate-90" />
                            </SidebarMenuSubButton>
                          </CollapsibleTrigger>
                          <CollapsibleContent className={collapsibleContentClass}>
                            <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                              {COMMITMENTS_GROUP.map(({ key, href, icon: Icon }) => {
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
                                        <TruncatingTooltip text={t(`nav.${key}`)} side="right" />
                                      </Link>
                                    </SidebarMenuSubButton>
                                  </SidebarMenuSubItem>
                                );
                              })}
                            </SidebarMenuSub>
                          </CollapsibleContent>
                        </SidebarMenuSubItem>
                      </Collapsible>
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

              {/* Portfolio collapsible group */}
              <Collapsible asChild defaultOpen={isPortfolioActive} className="group/collapsible">
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      size="lg"
                      className={cn(
                        '[&_svg]:size-5 text-paragraph-medium',
                        NAV_ITEM_STYLES,
                        !isPortfolioActive &&
                          'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                        isPortfolioActive && 'bg-gray-100',
                      )}
                    >
                      <TrendingUp />
                      <span>{t('navGroups.portfolio')}</span>
                      <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent className={collapsibleContentClass}>
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
                                <TruncatingTooltip text={t(`nav.${key}`)} side="right" />
                              </Link>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        );
                      })}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

              {/* Administration collapsible group — admins only (and only items matching the signup mode) */}
              {showAdminGroup && (
                <Collapsible asChild defaultOpen={isAdminActive} className="group/collapsible">
                  <SidebarMenuItem>
                    <CollapsibleTrigger asChild>
                      <SidebarMenuButton
                        size="lg"
                        className={cn(
                          '[&_svg]:size-5 text-paragraph-medium',
                          NAV_ITEM_STYLES,
                          !isAdminActive &&
                            'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                          isAdminActive && 'bg-gray-100',
                        )}
                      >
                        <ShieldCheck />
                        <span>{t('navGroups.administration')}</span>
                        <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                      </SidebarMenuButton>
                    </CollapsibleTrigger>
                    <CollapsibleContent className={collapsibleContentClass}>
                      <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                        {adminItems.map(({ key, href, icon: Icon }) => {
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
                                  <TruncatingTooltip text={t(`nav.${key}`)} side="right" />
                                </Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          );
                        })}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </SidebarMenuItem>
                </Collapsible>
              )}

              {/* Settings collapsible group */}
              <Collapsible asChild defaultOpen={isSettingsActive} className="group/collapsible">
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      size="lg"
                      className={cn(
                        '[&_svg]:size-5 text-paragraph-medium',
                        NAV_ITEM_STYLES,
                        !isSettingsActive &&
                          'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                        isSettingsActive && 'bg-gray-100',
                      )}
                    >
                      <Settings />
                      <span>{t('navGroups.settings')}</span>
                      <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent className={collapsibleContentClass}>
                    <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                      {SETTINGS_GROUP.map(({ key, href, icon: Icon }) => {
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
                                <TruncatingTooltip text={t(`nav.${key}`)} side="right" />
                              </Link>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        );
                      })}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>
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
              initialCollapsed={currencyCollapsed}
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
