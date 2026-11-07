import { useState } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AUTOSAVE_COALESCE_MS } from '@/lib/constants/autosave';
import {
  autosaveErrorMessage,
  AutosaveRefusal,
  useAutosaveToggles,
} from '@/lib/hooks/use-autosave-toggles';

/*
 * The optimistic toggle every self-saving switch is built on (the notification grid and cadence, a
 * pot's per-member access). Driven through a harness that behaves like those callers: its confirmed
 * state is what the "server" has accepted, and a write records the answer there before resolving.
 * Every write is held open until the test settles it, so the order answers arrive in is the test's.
 */

interface Call {
  key: string;
  value: boolean;
  resolve: () => void;
  reject: (error: unknown) => void;
}

function setup() {
  const calls: Call[] = [];
  const onError = vi.fn();
  const onSettled = vi.fn();
  const hook = renderHook(() => {
    const [server, setServer] = useState<Record<string, boolean>>({ a: false, b: false });
    const toggles = useAutosaveToggles<boolean>({
      confirmed: (key) => server[key]!,
      write: async (key, value) => {
        await new Promise<void>((resolve, reject) => calls.push({ key, value, resolve, reject }));
        setServer((current) => ({ ...current, [key]: value }));
      },
      onError,
      onSettled,
    });
    return { toggles, server };
  });
  return { calls, onError, onSettled, hook };
}

// Lets the coalescing wait run out.
async function settleBurst() {
  await act(async () => {
    vi.advanceTimersByTime(AUTOSAVE_COALESCE_MS);
  });
}

async function answer(call: Call, outcome: 'ok' | Error = 'ok') {
  await act(async () => {
    if (outcome === 'ok') call.resolve();
    else call.reject(outcome);
  });
}

describe('useAutosaveToggles', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('shows the new value the instant it is set, before anything is written', () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    expect(hook.result.current.toggles.value('a')).toBe(true);
    expect(calls).toHaveLength(0);
  });

  it('writes a burst of clicks once, with the final value', async () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('a', false));
    act(() => hook.result.current.toggles.set('a', true));
    await settleBurst();

    expect(calls.map(({ key, value }) => [key, value])).toEqual([['a', true]]);
    await answer(calls[0]!);
    expect(hook.result.current.server.a).toBe(true);
    expect(hook.result.current.toggles.value('a')).toBe(true);
    expect(hook.result.current.toggles.isPending('a')).toBe(false);
  });

  it('writes nothing for a double click that ends where it began', async () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('a', false));
    await settleBurst();

    expect(calls).toHaveLength(0);
    expect(hook.result.current.toggles.value('a')).toBe(false);
    expect(hook.result.current.toggles.isPending('a')).toBe(false);
  });

  it('holds a click made mid-write until that write answers, then writes the newest value', async () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    await settleBurst();
    expect(calls).toHaveLength(1);

    // Two more clicks while the first write is out: nothing is sent beside it.
    act(() => hook.result.current.toggles.set('a', false));
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('a', false));
    await settleBurst();
    expect(calls).toHaveLength(1);
    expect(hook.result.current.toggles.value('a')).toBe(false);

    await answer(calls[0]!);
    expect(calls.map(({ value }) => value)).toEqual([true, false]);
    await answer(calls[1]!);
    // The last intent is what the server ends with, and what the switch shows.
    expect(hook.result.current.server.a).toBe(false);
    expect(hook.result.current.toggles.value('a')).toBe(false);
  });

  it('keeps each control on its own value when their answers arrive out of order', async () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('b', true));
    await settleBurst();
    expect(calls.map(({ key }) => key)).toEqual(['a', 'b']);

    await answer(calls[1]!);
    await answer(calls[0]!);
    expect(hook.result.current.server).toEqual({ a: true, b: true });
    expect(hook.result.current.toggles.value('a')).toBe(true);
    expect(hook.result.current.toggles.value('b')).toBe(true);
  });

  it('rolls a failed control back to its confirmed value and reports it, leaving the others alone', async () => {
    const { calls, onError, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('b', true));
    await settleBurst();

    const failure = new AutosaveRefusal('Push is not configured on this server.');
    await answer(calls[0]!, failure);
    expect(hook.result.current.toggles.value('a')).toBe(false);
    expect(onError).toHaveBeenCalledExactlyOnceWith('a', failure);
    // The other control's write is still out, and still shows what was asked for.
    expect(hook.result.current.toggles.value('b')).toBe(true);
    expect(hook.result.current.toggles.isPending('b')).toBe(true);

    await answer(calls[1]!);
    expect(hook.result.current.server).toEqual({ a: false, b: true });
  });

  it('rolls back to the value the server last accepted, not to where the burst began', async () => {
    const { calls, onError, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    await settleBurst();
    act(() => hook.result.current.toggles.set('a', false));
    await answer(calls[0]!);
    await settleBurst();

    await answer(calls[1]!, new Error('network'));
    expect(onError).toHaveBeenCalledOnce();
    expect(hook.result.current.toggles.value('a')).toBe(true);
  });

  it('still sends the newest value when the control unmounts mid-write with a click waiting', async () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    await settleBurst();
    act(() => hook.result.current.toggles.set('a', false));
    hook.unmount();
    await answer(calls[0]!);
    expect(calls.map(({ value }) => value)).toEqual([true, false]);
  });

  it('tells the caller it has settled after a no-op burst and after a failure', async () => {
    const { calls, onSettled, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    act(() => hook.result.current.toggles.set('a', false));
    await settleBurst();
    expect(onSettled).toHaveBeenCalledTimes(1);

    act(() => hook.result.current.toggles.set('b', true));
    await settleBurst();
    await answer(calls[0]!, new Error('network'));
    expect(onSettled).toHaveBeenCalledTimes(2);
  });

  it('writes a pending burst at once when the control unmounts, rather than losing it', () => {
    const { calls, hook } = setup();
    act(() => hook.result.current.toggles.set('a', true));
    hook.unmount();
    expect(calls.map(({ key, value }) => [key, value])).toEqual([['a', true]]);
  });
});

describe('autosaveErrorMessage', () => {
  it("shows the server's refusal when it gave one, and the caller's message otherwise", () => {
    expect(autosaveErrorMessage(new AutosaveRefusal('Refused.'), 'Could not save.')).toBe(
      'Refused.',
    );
    expect(autosaveErrorMessage(new AutosaveRefusal(''), 'Could not save.')).toBe(
      'Could not save.',
    );
    expect(autosaveErrorMessage(new Error('boom'), 'Could not save.')).toBe('Could not save.');
  });
});
