import { describe, expect, it } from 'vitest';

import {
  activeNavigation,
  beginNavigation,
  linkDestination,
  pathOf,
  settleNavigation,
  type AnchorLike,
  type ClickLike,
} from '@/lib/navigation-pending';

/*
 * The rules of the navigation in flight, without a browser: which clicks start one, when one is over,
 * and which one wins. `NavigationPendingProvider` only wires these to the document and the router.
 */

const HERE = new URL('http://localhost:3000/expenses?page=2');
const PLAIN: ClickLike = {
  button: 0,
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
};

function anchor(href: string, attributes: Record<string, string> = {}): AnchorLike {
  return {
    href: new URL(href, HERE).href,
    target: attributes.target ?? '',
    hasAttribute: (name) => name in attributes,
  };
}

describe('linkDestination', () => {
  it('is the path + query of an in-app link', () => {
    expect(linkDestination(PLAIN, anchor('/dashboard'), HERE)).toBe('/dashboard');
    expect(linkDestination(PLAIN, anchor('/income?scope=mine'), HERE)).toBe('/income?scope=mine');
    expect(linkDestination(PLAIN, anchor('/income#top'), HERE)).toBe('/income');
  });

  it('ignores a click that opens elsewhere: modifiers, another button, a target, a download', () => {
    for (const key of ['metaKey', 'ctrlKey', 'shiftKey', 'altKey'] as const) {
      expect(
        linkDestination({ ...PLAIN, [key]: true }, anchor('/dashboard'), HERE),
        key,
      ).toBeNull();
    }
    expect(linkDestination({ ...PLAIN, button: 1 }, anchor('/dashboard'), HERE)).toBeNull();
    expect(linkDestination(PLAIN, anchor('/dashboard', { target: '_blank' }), HERE)).toBeNull();
    expect(linkDestination(PLAIN, anchor('/export.csv', { download: '' }), HERE)).toBeNull();
    // `_self` is this tab.
    expect(linkDestination(PLAIN, anchor('/dashboard', { target: '_self' }), HERE)).toBe(
      '/dashboard',
    );
  });

  it('ignores another origin and an in-page jump', () => {
    expect(linkDestination(PLAIN, anchor('https://example.com/dashboard'), HERE)).toBeNull();
    expect(linkDestination(PLAIN, anchor('#main-content'), HERE)).toBeNull();
    expect(linkDestination(PLAIN, anchor('/expenses?page=2#row-3'), HERE)).toBeNull();
  });

  it('keeps a link to the current URL, which is a navigation of its own', () => {
    expect(linkDestination(PLAIN, anchor('/expenses?page=2'), HERE)).toBe('/expenses?page=2');
  });
});

describe('a pending navigation', () => {
  it('starts, knowing whether it changes page', () => {
    expect(beginNavigation(1, '/expenses', '/dashboard')).toEqual({
      id: 1,
      from: '/expenses',
      to: '/dashboard',
      page: true,
    });
    expect(beginNavigation(2, '/expenses', '/expenses?page=3')?.page).toBe(false);
    expect(pathOf('/expenses?page=3')).toBe('/expenses');
  });

  it('is nothing to wait for when it goes to the URL already committed — and ends the one pending', () => {
    expect(beginNavigation(3, '/expenses', '/expenses')).toBeNull();
  });

  it('runs while the committed URL is the one it left, and is over once that moves', () => {
    const pending = beginNavigation(1, '/expenses', '/dashboard');
    expect(activeNavigation(pending, '/expenses')).toBe(pending);
    // Landed where it was going.
    expect(activeNavigation(pending, '/dashboard')).toBeNull();
    // Redirected, or ended on the error boundary at its own URL: over all the same.
    expect(activeNavigation(pending, '/login')).toBeNull();
    expect(activeNavigation(null, '/expenses')).toBeNull();
  });

  it('is replaced by a newer one, whose settle alone can end it', () => {
    const first = beginNavigation(1, '/expenses', '/dashboard');
    const second = beginNavigation(2, '/expenses', '/income');
    // The older one's transition ending in place does not end the newer one.
    expect(settleNavigation(second, 1)).toBe(second);
    expect(settleNavigation(second, 2)).toBeNull();
    expect(settleNavigation(first, 1)).toBeNull();
    expect(settleNavigation(null, 1)).toBeNull();
  });
});
