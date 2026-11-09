import { forwardRef, type ComponentProps, type ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GroupInviteDialog } from '@/app/(protected)/shared/[groupId]/_components/group-invite-dialog';
import type { GroupMember } from '@/lib/api/groups';
import messages from '../../translations/en.json';

/*
 * The invite dialog's mode — a first invite or a resend — is decided when it OPENS. Creating the link
 * refreshes the page behind the dialog so the seat reads "invited", and that refresh hands the dialog a
 * member whose `hasPendingInvite` is now true. Read live, a first-ever invite then turned into "Send a
 * new link / This replaces …'s current link" while the brand-new link was still on screen.
 */

const actions = vi.hoisted(() => ({ createGroupInvite: vi.fn() }));
vi.mock('@/app/(protected)/shared/group-actions', () => actions);

// Radix cannot mount in this suite (a second React copy), so the dialog's parts are plain elements.
vi.mock('@repo/ui/components', () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Input = forwardRef<HTMLInputElement, ComponentProps<'input'>>(function Input(props, ref) {
    return <input ref={ref} {...props} />;
  });
  return {
    Button: (props: ComponentProps<'button'> & { blue?: boolean }) => (
      <button
        type="button"
        {...Object.fromEntries(Object.entries(props).filter(([name]) => name !== 'blue'))}
      />
    ),
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
      open ? <div>{children}</div> : null,
    DialogContent: passthrough,
    DialogDescription: ({ children }: { children: ReactNode }) => (
      <p data-testid="description">{children}</p>
    ),
    DialogFooter: passthrough,
    DialogHeader: passthrough,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
    Hint: (props: ComponentProps<'p'>) => <p {...props} />,
    Input,
    Label: (props: ComponentProps<'label'>) => <label {...props} />,
    Separator: () => <hr />,
  };
});

const COPY = messages.shared.invite;

function member(hasPendingInvite: boolean): GroupMember {
  return {
    id: 7,
    displayName: 'Ana',
    role: 'member',
    isActive: true,
    isLinked: false,
    isSelf: false,
    hasPendingInvite,
    joinedAt: null,
    createdAt: '2026-11-01T00:00:00Z',
    updatedAt: '2026-11-01T00:00:00Z',
  };
}

function dialog(open: boolean, seat: GroupMember) {
  return (
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <GroupInviteDialog
        open={open}
        onOpenChange={() => {}}
        groupId={1}
        member={seat}
        onSuccess={() => {}}
      />
    </NextIntlClientProvider>
  );
}

beforeEach(() => {
  actions.createGroupInvite.mockReset().mockResolvedValue({
    ok: true,
    inviteUrl: 'https://renly.test/join?token=abc',
    email: 'ana@example.com',
    expiresAt: '2026-11-15T00:00:00Z',
  });
});

describe('the group invite dialog', () => {
  it('stays a first invite after the refresh that follows creating the link', async () => {
    const { rerender } = render(dialog(true, member(false)));
    expect(screen.getByRole('heading')).toHaveTextContent(COPY.title);

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ana@example.com' } });
    await act(async () => {
      fireEvent.submit(screen.getByRole('textbox').closest('form')!);
    });
    expect(actions.createGroupInvite).toHaveBeenCalled();

    // "Also emailed to…" is information, not a warning: it carries the info icon.
    const sentTo = screen.getByText('Also emailed to ana@example.com.');
    const hint = sentTo.closest('[class*="flex items-center"]')!;
    expect(hint.querySelector('svg.lucide-info')).not.toBeNull();
    expect(hint.querySelector('svg.lucide-triangle-alert, svg.lucide-alert-triangle')).toBeNull();

    // The page behind it refreshed: the seat now has a pending invite.
    rerender(dialog(true, member(true)));
    expect(screen.getByRole('heading')).toHaveTextContent(COPY.title);
    expect(screen.getByTestId('description')).toHaveTextContent('Send Ana a link');
  });

  it('opens as a resend for a seat that already has a link out', () => {
    const { rerender } = render(dialog(false, member(false)));
    rerender(dialog(true, member(true)));
    expect(screen.getByRole('heading')).toHaveTextContent(COPY.resendTitle);
  });
});
