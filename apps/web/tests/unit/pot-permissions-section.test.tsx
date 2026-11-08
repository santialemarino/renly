import { createElement, type ReactNode } from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PotPermissionsSection } from '@/app/(protected)/shared/pots/[id]/_components/pot-permissions-section';
import type { Group, GroupMember } from '@/lib/api/groups';
import type { Pot } from '@/lib/api/pots';
import { AUTOSAVE_COALESCE_MS } from '@/lib/constants/autosave';
import messages from '../../translations/en.json';

/*
 * The pot's per-seat switches save on their own. A save that lands is kept as the seat's explicit row
 * (the switch stays where it was put, the source reads "Set here") and refreshes the page only when it
 * changed the viewer's OWN access; a refused save puts the seat back on its effective access and shows
 * the server's words, with no refresh.
 *
 * Radix's Switch cannot render here (two React copies; see the testing skill), so the base components
 * are stood in for by plain elements that keep the props the section relies on.
 */

vi.mock('@repo/ui/components', () => {
  const plain =
    (tag: string) =>
    ({ children }: { children?: ReactNode }) =>
      createElement(tag, null, children);
  return {
    Badge: plain('span'),
    Table: plain('table'),
    TableBody: plain('tbody'),
    TableCell: plain('td'),
    TableHead: plain('th'),
    TableHeader: plain('thead'),
    TableRow: plain('tr'),
    Switch: ({
      checked,
      disabled,
      onCheckedChange,
      'aria-label': label,
    }: {
      checked: boolean;
      disabled?: boolean;
      onCheckedChange: (next: boolean) => void;
      'aria-label'?: string;
    }) =>
      createElement('button', {
        type: 'button',
        role: 'switch',
        disabled,
        'aria-label': label,
        'aria-checked': checked,
        onClick: () => onCheckedChange(!checked),
      }),
  };
});

vi.mock('@/components/row-action-button', () => ({ RowActionButton: () => null }));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const refresh = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));

const pending = vi.hoisted(
  () =>
    [] as {
      memberId: number;
      access: { canView: boolean; canWrite: boolean };
      resolve: (result: { ok: boolean; conflictDetail?: string }) => void;
    }[],
);

vi.mock('@/app/(protected)/shared/pot-actions', () => ({
  clearPotPermission: vi.fn(),
  setPotPermission: (
    _potId: number,
    memberId: number,
    access: { canView: boolean; canWrite: boolean },
  ) => new Promise((resolve) => pending.push({ memberId, access, resolve })),
}));

const SELF = 1;
const OTHER = 2;

function member(id: number, displayName: string, isSelf: boolean): GroupMember {
  return {
    id,
    displayName,
    role: 'admin',
    isActive: true,
    isLinked: true,
    isSelf,
    hasPendingInvite: false,
    joinedAt: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  };
}

const GROUP = {
  id: 7,
  name: 'Home',
  kind: 'household',
  myRole: 'admin',
  activeMemberCount: 2,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  members: [member(SELF, 'Me', true), member(OTHER, 'Sam', false)],
} as Group;

// A private pot with no explicit rows: every seat starts with view and write off.
const POT = { id: 3, groupId: 7, visibility: 'private', permissions: [] } as unknown as Pot;

const en = messages.shared.pots.permissions;

function row(name: string) {
  return screen.getByText(name).closest('tr') as HTMLElement;
}

function viewSwitch(name: string) {
  return within(row(name)).getByRole('switch', { name: en.table.view });
}

function renderSection() {
  render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <PotPermissionsSection pot={POT} group={GROUP} />
    </NextIntlClientProvider>,
  );
}

async function flushBurst() {
  await act(async () => {
    vi.advanceTimersByTime(AUTOSAVE_COALESCE_MS);
  });
}

describe('the pot permissions section', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    pending.length = 0;
    refresh.mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
  });
  afterEach(() => vi.useRealTimers());

  it("keeps a landed save as the seat's own row and refreshes only for the viewer's own access", async () => {
    renderSection();

    fireEvent.click(viewSwitch('Sam'));
    await flushBurst();
    expect(pending).toHaveLength(1);
    expect(pending[0]).toMatchObject({
      memberId: OTHER,
      access: { canView: true, canWrite: false },
    });

    await act(async () => pending[0]!.resolve({ ok: true }));
    expect(viewSwitch('Sam')).toHaveAttribute('aria-checked', 'true');
    expect(within(row('Sam')).getByText(en.explicit)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith(en.success);
    // Another seat's access changes nothing the viewer's page is drawn from.
    expect(refresh).not.toHaveBeenCalled();

    fireEvent.click(viewSwitch('Me'));
    await flushBurst();
    await act(async () => pending[1]!.resolve({ ok: true }));
    expect(viewSwitch('Me')).toHaveAttribute('aria-checked', 'true');
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("puts a refused seat back on its effective access and shows the server's words", async () => {
    renderSection();

    fireEvent.click(viewSwitch('Me'));
    await flushBurst();
    // Optimistic while the write is out.
    expect(viewSwitch('Me')).toHaveAttribute('aria-checked', 'true');
    expect(within(row('Me')).getByText(en.explicit)).toBeInTheDocument();

    await act(async () => pending[0]!.resolve({ ok: false, conflictDetail: 'Not allowed.' }));
    expect(viewSwitch('Me')).toHaveAttribute('aria-checked', 'false');
    expect(within(row('Me')).getByText(en.inherited)).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('Not allowed.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
});
