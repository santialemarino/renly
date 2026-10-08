import {
  Children,
  cloneElement,
  Fragment,
  isValidElement,
  useContext,
  type ReactElement,
  type ReactNode,
} from 'react';
import { render } from '@testing-library/react';
import { MotionConfigContext } from 'motion/react';
import { describe, expect, it, vi } from 'vitest';

import RootLayout from '@/app/layout';

// The layout's stylesheet and font are build-time concerns with nothing to say about the tree.
vi.mock('@/app/globals.css', () => ({}));
vi.mock('next/font/local', () => ({ default: () => ({ className: 'font' }) }));
// The real provider infers its locale from the server request, which a test has none of. Passing the
// children through keeps it on the path to the page without asserting anything about next-intl.
vi.mock('next-intl', () => ({
  NextIntlClientProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('next-intl/server', () => ({
  getLocale: async () => 'en',
  getMessages: async () => ({}),
  getTranslations: async () => (key: string) => key,
}));

/*
 * Every motion/react animation in the app honours `prefers-reduced-motion` only because the root
 * layout hands the whole tree a MotionConfig with `reducedMotion="user"`; without one, motion/react
 * defaults to "never" and every call site plays in full under `reduce`. Nothing per-call-site can
 * show the gap: each component type-checks and animates the same way either way.
 *
 * So this asks the question from the consumer's side rather than looking for a component by name. It
 * renders the tree the root layout actually returns, and puts a probe that reads the motion config
 * context at EVERY place something can render: where the page goes (`children`), and in place of each
 * element the layout renders beside it (the cookie banner, the toaster, anything added later). Every
 * probe must see "user". A provider that wraps only `children`, or one removed, or one set to another
 * value, turns at least one probe red — and whatever wraps the page is found by walking, not named.
 */

const seen = new Map<string, string | undefined>();

function Probe({ at }: { at: string }) {
  seen.set(at, useContext(MotionConfigContext).reducedMotion);
  return null;
}

const PAGE = <Probe at="children" />;

// Identified by type and prop, not identity: `Children.toArray` re-keys (clones) what it returns.
function isPage(node: ReactNode): boolean {
  return (
    isValidElement(node) && node.type === Probe && (node.props as { at: string }).at === 'children'
  );
}

function childrenOf(node: ReactElement): ReactNode[] {
  return Children.toArray((node.props as { children?: ReactNode }).children);
}

function containsPage(node: ReactNode): boolean {
  return isPage(node) || (isValidElement(node) && childrenOf(node).some(containsPage));
}

function nameOf(element: ReactElement): string {
  const { type } = element;
  if (typeof type === 'string') {
    return type;
  }
  const named = type as { displayName?: string; name?: string; render?: { name?: string } };
  return named.displayName ?? named.name ?? named.render?.name ?? 'anonymous';
}

/*
 * Keeps everything on the path to the page (so the real providers render around it), replaces every
 * element off that path with a probe, and unwraps `<html>` / `<body>`, which cannot mount inside the
 * test's container.
 */
function probeTree(node: ReactNode, index = 0): ReactNode {
  if (!isValidElement(node) || isPage(node)) {
    return node;
  }
  if (!containsPage(node)) {
    return <Probe key={index} at={`${nameOf(node)}#${index}`} />;
  }
  const mapped = childrenOf(node).map((child, i) => probeTree(child, i));
  if (node.type === 'html' || node.type === 'body') {
    return <Fragment key={index}>{mapped}</Fragment>;
  }
  return cloneElement(node, undefined, ...mapped);
}

describe('the root layout motion config', () => {
  it('hands every element it renders reducedMotion="user"', async () => {
    seen.clear();
    const tree = await RootLayout({ children: PAGE });
    render(<>{probeTree(tree)}</>);

    // The probes must actually have run, including beside the page: a walk that found nothing would
    // otherwise pass on an empty map.
    expect(seen.get('children')).toBeDefined();
    expect(seen.size).toBeGreaterThan(1);
    expect(Object.fromEntries(seen)).toEqual(
      Object.fromEntries([...seen.keys()].map((at) => [at, 'user'])),
    );
  });
});
