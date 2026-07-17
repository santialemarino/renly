'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  ArrowDownUp,
  BarChart3,
  Bell,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  CreditCard,
  FileText,
  FolderOpen,
  Globe,
  HelpCircle,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  ListChecks,
  LogOut,
  MessageSquare,
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
  type LucideIcon,
} from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
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
import { FeedbackDialog } from '@/app/(protected)/_components/feedback-dialog';
import { TruncatingTooltip } from '@/app/(protected)/_components/truncating-tooltip';
import { userSignOut } from '@/auth';
import { Brand } from '@/components/brand';
import { COOKIE_MAX_AGE_1_YEAR, SIDEBAR_EXPANDED_COOKIE } from '@/config/constants';
import { ALL_ROUTE_PATHS, LOGIN_ROUTE, ROUTES } from '@/config/routes';
import type { SignupMode } from '@/lib/auth-api';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';

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
  { key: 'data', href: ROUTES.data, icon: ArrowDownUp },
  { key: 'integrations', href: ROUTES.integrations, icon: Puzzle },
] as const;

// Admin-only group (rendered only when the user is an admin). Items can be gated further:
// invitePeople is only relevant in invite mode (in open mode anyone signs up, so there's no one to invite).
const ADMIN_GROUP = [
  { key: 'invitePeople', href: ROUTES.admin, icon: UserPlus, inviteOnly: true },
  { key: 'feedback', href: ROUTES.adminFeedback, icon: Inbox, inviteOnly: false },
] as const;

/*
 * Progressive disclosure (UX-7): advanced nav items hidden from a first-run newcomer until they
 * have data OR reveal them via "Show more". Keyed by nav `key`; the Commitments subgroup is gated
 * as a whole via `advancedVisible`. The layout decides the initial state; the sidebar animates it.
 */
const ADVANCED_NAV_KEYS = new Set<string>(['creditCards', 'groups']);

// Every known route path, for the active-state check below: a sub-path that is itself a distinct
// route is a sibling, not a child, so its parent (e.g. /admin vs /admin/feedback) shouldn't light up.
const ROUTE_PATH_SET = new Set<string>(ALL_ROUTE_PATHS);

/** Shared interactive states for all nav items (main buttons and sub-buttons). */
const NAV_ITEM_STYLES =
  'hover:bg-gray-100 active:bg-gray-200 focus-visible:bg-gray-100 focus-visible:outline-none focus-visible:ring-0 data-[active=true]:bg-blue-800 data-[active=true]:text-white data-[active=true]:hover:bg-blue-900 data-[active=true]:active:bg-blue-950 data-[active=true]:focus-visible:bg-blue-900';

/** Extra styles for SidebarMenuSubButton: hover text color (matching the main button primitive), transition, and svg icon animation. */
const SUB_BUTTON_EXTRAS =
  'hover:text-sidebar-accent-foreground focus-visible:text-sidebar-accent-foreground transition-[background-color,color] duration-200 ease-out [&_svg]:transition-transform [&_svg]:duration-200 [&_svg]:ease-out';

/*
 * Animates an advanced sub-item's reveal/collapse (height + opacity, both directions) when a
 * newcomer toggles "Show more". It IS the `<li>` (matching SidebarMenuSubItem's markup) so the
 * `<ul>` stays valid. `AnimatePresence initial={false}` suppresses the enter animation on first
 * paint; reduced motion collapses it to an instant show/hide.
 */
function RevealSubItem({
  show,
  reduce,
  children,
}: {
  show: boolean;
  reduce: boolean;
  children: React.ReactNode;
}) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.li
          data-slot="sidebar-menu-sub-item"
          data-sidebar="menu-sub-item"
          className="group/menu-sub-item relative"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: reduce ? 0 : ANIMATION_DEFAULT }}
          style={{ overflow: 'hidden' }}
        >
          {children}
        </motion.li>
      )}
    </AnimatePresence>
  );
}

/*
 * A leaf nav sub-item (icon + label linking to a route). Advanced items animate their reveal via
 * RevealSubItem; the rest render as a plain sub-item. Shared by every uniform leaf nav list.
 */
function NavSubItem({
  href,
  onClick,
  icon: Icon,
  label,
  active,
  advanced = false,
  advancedVisible = true,
  reduce = false,
}: {
  href?: string;
  onClick?: () => void;
  icon: LucideIcon;
  label: string;
  active: boolean;
  advanced?: boolean;
  advancedVisible?: boolean;
  reduce?: boolean;
}) {
  const subButtonClass = cn(
    'h-8 text-paragraph-sm-medium',
    NAV_ITEM_STYLES,
    SUB_BUTTON_EXTRAS,
    !active && 'hover:[&_svg]:rotate-12 focus-visible:[&_svg]:rotate-12',
  );
  const inner = (
    <>
      <Icon />
      <TruncatingTooltip text={label} side="right" />
    </>
  );
  // A leaf sub-item is either a link (href) or an in-place action (onClick, e.g. opening a dialog).
  const button = (
    <SidebarMenuSubButton asChild isActive={active} className={subButtonClass}>
      {href ? (
        <Link href={href}>{inner}</Link>
      ) : (
        <button type="button" onClick={onClick}>
          {inner}
        </button>
      )}
    </SidebarMenuSubButton>
  );

  if (advanced) {
    return (
      <RevealSubItem show={advancedVisible || active} reduce={reduce}>
        {button}
      </RevealSubItem>
    );
  }
  return <SidebarMenuSubItem>{button}</SidebarMenuSubItem>;
}

interface AppSidebarProps {
  displayCurrencies: string[];
  activeCurrency: string;
  supportedCurrencies: string[] | undefined;
  currencyCollapsed: boolean;
  isAdmin: boolean;
  signupMode: SignupMode;
  initialExpanded: boolean;
  showDisclosureToggle: boolean;
}

export function AppSidebar({
  displayCurrencies,
  activeCurrency,
  supportedCurrencies,
  currencyCollapsed,
  isAdmin,
  signupMode,
  initialExpanded,
  showDisclosureToggle,
}: AppSidebarProps) {
  const t = useTranslations('sidebar');
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  /*
   * A newcomer's client-side "Show more" state (seeded from the server's cookie-derived value) so
   * revealing/collapsing the advanced items animates without a server round-trip.
   */
  const [expandedByUser, setExpandedByUser] = useState(initialExpanded);
  const reduce = useReducedMotion() ?? false;

  // Active on the exact path, or on a deeper sub-path that isn't itself a distinct route (so /admin
  // doesn't light up on the sibling /admin/feedback).
  const isActive = (href: string) =>
    pathname === href || (pathname.startsWith(href + '/') && !ROUTE_PATH_SET.has(pathname));
  const isCommitmentsActive = COMMITMENTS_GROUP.some(({ href }) => isActive(href));
  // Finances "section" is active when any direct child or any nested Commitments child is active.
  const isFinancesActive = FINANCES_GROUP.some(({ href }) => isActive(href)) || isCommitmentsActive;
  const isPortfolioActive = PORTFOLIO_GROUP.some(({ href }) => isActive(href));
  const isSettingsActive = SETTINGS_GROUP.some(({ href }) => isActive(href));

  // A newcomer's advanced items follow their toggle; everyone else always sees them.
  const advancedVisible = showDisclosureToggle ? expandedByUser : true;

  // Admin group: only for admins, and only items whose gate matches (invitePeople → invite mode).
  // When no item qualifies (e.g. open mode), the whole group is hidden.
  const adminItems = ADMIN_GROUP.filter((item) => !item.inviteOnly || signupMode === 'invite');
  const showAdminGroup = isAdmin && adminItems.length > 0;
  const isAdminActive = adminItems.some(({ href }) => isActive(href));

  // Suppress collapsible animation on first render so open groups don't animate in.
  const collapsibleContentClass = mounted
    ? 'overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up'
    : 'overflow-hidden';

  useEffect(() => setMounted(true), []);

  async function handleLogout() {
    setLoggingOut(true);
    await userSignOut();
    router.push(LOGIN_ROUTE);
  }

  // Toggle a newcomer's "Show more"/"Show fewer" choice. Client state drives the reveal animation;
  // the cookie persists it so a full reload (server layout) restores the same state.
  function handleToggleDisclosure() {
    const next = !expandedByUser;
    setExpandedByUser(next);
    document.cookie = `${SIDEBAR_EXPANDED_COOKIE}=${next}; path=/; max-age=${COOKIE_MAX_AGE_1_YEAR}`;
  }

  return (
    <Sidebar className="border-sidebar-border shadow-lg">
      <SidebarHeader className="pl-4 py-5 border-b border-sidebar-border">
        <Brand name={t('brand')} size="lg" />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="p-4">
          <SidebarGroupContent>
            <SidebarMenu className="gap-y-2" data-testid="sidebar-nav">
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
                      {FINANCES_GROUP.map(({ key, href, icon }) => (
                        <NavSubItem
                          key={key}
                          href={href}
                          icon={icon}
                          label={t(`nav.${key}`)}
                          active={isActive(href)}
                          advanced={ADVANCED_NAV_KEYS.has(key)}
                          advancedVisible={advancedVisible}
                          reduce={reduce}
                        />
                      ))}

                      {/* Nested Commitments subgroup — hidden from a first-run newcomer (progressive disclosure) unless active. */}
                      <RevealSubItem show={advancedVisible || isCommitmentsActive} reduce={reduce}>
                        <Collapsible
                          defaultOpen={isCommitmentsActive}
                          className="group/inner-collapsible"
                        >
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
                              {COMMITMENTS_GROUP.map(({ key, href, icon }) => (
                                <NavSubItem
                                  key={key}
                                  href={href}
                                  icon={icon}
                                  label={t(`nav.${key}`)}
                                  active={isActive(href)}
                                />
                              ))}
                            </SidebarMenuSub>
                          </CollapsibleContent>
                        </Collapsible>
                      </RevealSubItem>
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
                      {PORTFOLIO_GROUP.map(({ key, href, icon }) => (
                        <NavSubItem
                          key={key}
                          href={href}
                          icon={icon}
                          label={t(`nav.${key}`)}
                          active={isActive(href)}
                          advanced={ADVANCED_NAV_KEYS.has(key)}
                          advancedVisible={advancedVisible}
                          reduce={reduce}
                        />
                      ))}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>

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
                      {SETTINGS_GROUP.map(({ key, href, icon }) => (
                        <NavSubItem
                          key={key}
                          href={href}
                          icon={icon}
                          label={t(`nav.${key}`)}
                          active={isActive(href)}
                        />
                      ))}
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
                        {adminItems.map(({ key, href, icon }) => (
                          <NavSubItem
                            key={key}
                            href={href}
                            icon={icon}
                            label={t(`nav.${key}`)}
                            active={isActive(href)}
                          />
                        ))}
                      </SidebarMenuSub>
                    </CollapsibleContent>
                  </SidebarMenuItem>
                </Collapsible>
              )}

              {/* Progressive disclosure (UX-7): let a first-run newcomer reveal the advanced modules.
                  Animates in/out as the newcomer status changes; the label crossfades on toggle. */}
              <AnimatePresence initial={false}>
                {showDisclosureToggle && (
                  <motion.li
                    data-slot="sidebar-menu-item"
                    data-sidebar="menu-item"
                    className="group/menu-item relative"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: reduce ? 0 : ANIMATION_DEFAULT }}
                    style={{ overflow: 'hidden' }}
                  >
                    <SidebarMenuButton
                      onClick={handleToggleDisclosure}
                      aria-expanded={expandedByUser}
                      size="lg"
                      className={cn(
                        '[&_svg]:size-5 text-paragraph-medium text-muted-foreground',
                        NAV_ITEM_STYLES,
                      )}
                    >
                      <ChevronDown
                        className={cn(
                          'transition-transform duration-200',
                          expandedByUser && 'rotate-180',
                        )}
                      />
                      <AnimatePresence mode="popLayout" initial={false}>
                        <motion.span
                          key={expandedByUser ? 'less' : 'more'}
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          transition={{ duration: reduce ? 0 : ANIMATION_FAST }}
                        >
                          {expandedByUser ? t('showLess') : t('showMore')}
                        </motion.span>
                      </AnimatePresence>
                    </SidebarMenuButton>
                  </motion.li>
                )}
              </AnimatePresence>
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
              supportedCurrencies={supportedCurrencies}
              initialCollapsed={currencyCollapsed}
            />
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-sidebar-border">
        <SidebarMenu>
          {/* Support — a collapsible utility group (Help + Send feedback). Content sits BELOW the
              trigger (a normal expand-down, same as the other sidebar groups); because the footer is
              bottom-anchored and Log out stays pinned, the whole group rises to make room — so it
              reads as expanding downward while Log out never moves. Core (never hidden by
              progressive disclosure). */}
          <Collapsible asChild className="group/collapsible">
            <SidebarMenuItem>
              <CollapsibleTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className={cn(
                    '[&_svg]:size-5 text-paragraph-medium',
                    NAV_ITEM_STYLES,
                    'hover:[&>svg:first-child]:rotate-12 focus-visible:[&>svg:first-child]:rotate-12',
                  )}
                >
                  <LifeBuoy />
                  <span>{t('navGroups.support')}</span>
                  <ChevronRight className="ml-auto size-4! transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                </SidebarMenuButton>
              </CollapsibleTrigger>
              <CollapsibleContent className={collapsibleContentClass}>
                <SidebarMenuSub className="mx-4 mt-1 px-0 gap-1 border-l-0">
                  <NavSubItem
                    href={ROUTES.help}
                    icon={HelpCircle}
                    label={t('nav.help')}
                    active={isActive(ROUTES.help)}
                  />
                  <NavSubItem
                    onClick={() => setFeedbackOpen(true)}
                    icon={MessageSquare}
                    label={t('nav.sendFeedback')}
                    active={false}
                  />
                </SidebarMenuSub>
              </CollapsibleContent>
            </SidebarMenuItem>
          </Collapsible>

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

      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
    </Sidebar>
  );
}
