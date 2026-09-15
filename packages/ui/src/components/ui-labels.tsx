'use client';

import * as React from 'react';

/*
 * The handful of strings this package renders itself.
 *
 * Every other string in @repo/ui arrives from the app as children or a prop, because a design-system
 * package has no business owning product copy. These do not: they are accessible names on affordances
 * the primitives build internally (a dialog's close ✕, a search field's clear button, the pagination
 * arrows), so no call site is in a position to pass them without every call site passing them — which
 * is the enumerated list this repo keeps shipping defects through.
 *
 * So they come from one context instead, defaulted to English. The package stays usable with no
 * provider mounted (the defaults ARE the previous hardcoded strings, so an app that ignores this gets
 * exactly today's behaviour), and an app that wants them translated mounts the provider once.
 */
export interface UiLabels {
  // Dialog and Sheet close ✕.
  close: string;
  // SearchInput's clear button.
  clear: string;
  // Name of the pagination <nav> landmark.
  pagination: string;
  previousPage: string;
  nextPage: string;
  // SidebarTrigger and SidebarRail.
  toggleSidebar: string;
  // Accessible name and description of the mobile sidebar, which is a Sheet and therefore a dialog.
  sidebarTitle: string;
  sidebarDescription: string;
}

export const DEFAULT_UI_LABELS: UiLabels = {
  close: 'Close',
  clear: 'Clear',
  pagination: 'Pagination',
  previousPage: 'Go to previous page',
  nextPage: 'Go to next page',
  toggleSidebar: 'Toggle sidebar',
  sidebarTitle: 'Sidebar',
  sidebarDescription: "The app's navigation, shown as a panel on small screens.",
};

const UiLabelsContext = React.createContext<UiLabels>(DEFAULT_UI_LABELS);

interface UiLabelsProviderProps {
  // Partial so an app can translate some and inherit the English default for the rest.
  labels?: Partial<UiLabels>;
  children: React.ReactNode;
}

// Supplies translated accessible names to the primitives in this package. Mount once, near the root.
export function UiLabelsProvider({ labels, children }: UiLabelsProviderProps) {
  const value = React.useMemo(() => ({ ...DEFAULT_UI_LABELS, ...labels }), [labels]);

  return <UiLabelsContext.Provider value={value}>{children}</UiLabelsContext.Provider>;
}

// Reads the labels. Falls back to the English defaults when no provider is mounted.
export function useUiLabels(): UiLabels {
  return React.useContext(UiLabelsContext);
}
