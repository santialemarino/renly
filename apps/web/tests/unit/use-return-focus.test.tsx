import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useReturnFocus } from '@repo/ui/hooks';

/*
 * `useReturnFocus`, the hook both base overlays (`DialogContent`, `SheetContent`) hang their content
 * ref and Radix's close event on. Plain React over the real DOM — no Radix primitive — so, unlike its
 * consumers, it can be driven here: the overlay's content is a `role="dialog"` element, its mount is the
 * ref being called with it, and the close is Radix's event fired AFTER the content has left the
 * document. The browser half — that the wrappers really wire both — is
 * `tests/e2e/focus-system.auth.spec.ts`.
 */

function button(label: string, parent: HTMLElement = document.body): HTMLButtonElement {
  const element = document.createElement('button');
  element.textContent = label;
  parent.appendChild(element);
  return element;
}

function overlay(): HTMLDivElement {
  const content = document.createElement('div');
  content.setAttribute('role', 'dialog');
  document.body.appendChild(content);
  return content;
}

// What FocusScope dispatches: a cancelable event whose target is the content element.
function focusEvent(content: HTMLElement): Event {
  const event = new CustomEvent('focusScope.autoFocus', { cancelable: true });
  Object.defineProperty(event, 'target', { value: content });
  return event;
}

// Mounts an overlay whose opener is whatever holds focus now, then moves focus inside it.
function open(content: HTMLElement) {
  const { result } = renderHook(() => useReturnFocus({}));
  result.current.ref(content);
  button('inside', content).focus();
  return result;
}

// Closes it the way Radix does: the content leaves the document, then the close event fires.
function close(content: HTMLElement, handlers: ReturnType<typeof useReturnFocus>): Event {
  content.remove();
  const event = focusEvent(content);
  handlers.onCloseAutoFocus(event);
  return event;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useReturnFocus', () => {
  it('returns focus to the element that held it when the overlay opened', () => {
    const opener = button('open');
    opener.focus();
    const content = overlay();
    const handlers = open(content);

    // Premise: closing really does drop focus to <body>, which is the defect.
    content.remove();
    expect(document.activeElement).toBe(document.body);

    handlers.current.onCloseAutoFocus(focusEvent(content));
    expect(document.activeElement).toBe(opener);
  });

  it('falls back to the last element pressed when nothing held focus', () => {
    // A trigger that disables itself while it loads (the quick-add) drops focus before the overlay
    // exists; Safari never focuses a clicked button at all. The press is what is left to go on.
    const opener = button('open');
    opener.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(document.activeElement).toBe(document.body);
    const content = overlay();
    const handlers = open(content);

    close(content, handlers.current);
    expect(document.activeElement).toBe(opener);
  });

  it('follows the outer overlay’s chain when the opener has gone', () => {
    // A follow-up dialog (the amount-mismatch prompt) opened from a control INSIDE a form that is
    // still closing, which then goes.
    const trigger = button('add');
    trigger.focus();
    const outgoing = overlay();
    const outgoingHandlers = open(outgoing);

    const swapControl = button('switch form', outgoing);
    swapControl.focus();
    const incoming = overlay();
    const incomingHandlers = open(incoming);

    // The outgoing form finishes closing while focus is in the incoming one — it must not pull it out.
    close(outgoing, outgoingHandlers.current);
    expect(incoming.contains(document.activeElement)).toBe(true);

    close(incoming, incomingHandlers.current);
    expect(swapControl.isConnected).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });

  it('leaves focus alone when it has already landed somewhere real', () => {
    // A swap: the incoming form holds focus by the time the outgoing one's close fires.
    const opener = button('open');
    opener.focus();
    const outgoing = overlay();
    const handlers = open(outgoing);
    const incoming = button('incoming field');
    incoming.focus();

    const event = close(outgoing, handlers.current);
    expect(document.activeElement).toBe(incoming);
    // Still prevented, so Radix's own handler cannot move it to a Dialog.Trigger either.
    expect(event.defaultPrevented).toBe(true);
  });

  it('skips an opener that can no longer take focus', () => {
    const hamburger = button('menu');
    hamburger.focus();
    const sheet = overlay();
    open(sheet);
    const inner = button('inner', sheet);
    inner.focus();
    const form = overlay();
    const formHandlers = open(form);

    inner.disabled = true;
    close(form, formHandlers.current);
    expect(document.activeElement).toBe(hamburger);
  });

  it('lets the caller take over by preventing the default', () => {
    const opener = button('open');
    opener.focus();
    const content = overlay();
    const { result } = renderHook(() =>
      useReturnFocus({ onCloseAutoFocus: (event) => event.preventDefault() }),
    );
    result.current.ref(content);
    button('inside', content).focus();

    close(content, result.current);
    expect(document.activeElement).toBe(document.body);
  });

  it('defers to Radix when it recorded no opener at all', () => {
    const content = overlay();
    const { result } = renderHook(() => useReturnFocus({}));
    // Nothing focused and nothing pressed since the last test's DOM was cleared.
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    result.current.ref(content);

    const event = close(content, result.current);
    expect(event.defaultPrevented).toBe(false);
  });

  it('finds the opener when the content already took focus with autoFocus', () => {
    // React applies `autoFocus` before the overlay can look (the type-to-confirm deletes focus their
    // input), and Radix then skips its open event entirely — so focus is INSIDE by the time we record.
    const opener = button('delete');
    opener.focus();
    const content = overlay();
    const input = document.createElement('input');
    content.appendChild(input);
    input.focus();
    expect(content.contains(document.activeElement)).toBe(true);

    const { result } = renderHook(() => useReturnFocus({}));
    result.current.ref(content);
    close(content, result.current);
    expect(document.activeElement).toBe(opener);
  });

  it('records a fresh opener on every opening', () => {
    // The same dialog instance opened twice from two different buttons must go back to the second.
    const first = button('first');
    const second = button('second');
    const { result } = renderHook(() => useReturnFocus({}));

    first.focus();
    const once = overlay();
    result.current.ref(once);
    close(once, result.current);
    expect(document.activeElement).toBe(first);

    second.focus();
    const twice = overlay();
    const input = document.createElement('input');
    twice.appendChild(input);
    input.focus();
    result.current.ref(twice);
    close(twice, result.current);
    expect(document.activeElement).toBe(second);
  });

  it('keeps the opener when the ref is called again for the same element', () => {
    // React re-invokes a ref whose composed wrapper changed identity, on an ordinary re-render —
    // by then focus is inside the dialog or in something it opened, and must not become the opener.
    const opener = button('open');
    opener.focus();
    const content = overlay();
    const handlers = open(content);
    const elsewhere = button('a portaled option');
    elsewhere.focus();
    handlers.current.ref(null);
    handlers.current.ref(content);
    elsewhere.remove();
    button('inside again', content).focus();

    close(content, handlers.current);
    expect(document.activeElement).toBe(opener);
  });

  it('forwards the caller’s ref', () => {
    const content = overlay();
    const callerRef = { current: null as HTMLElement | null };
    const { result } = renderHook(() => useReturnFocus({ ref: callerRef }));
    result.current.ref(content);
    expect(callerRef.current).toBe(content);
  });
});
