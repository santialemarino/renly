import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DEFAULT_UI_LABELS, UiLabelsProvider, useUiLabels } from '@repo/ui/components';

/*
 * The merge inside `UiLabelsProvider`, which is one spread and the whole point of the context.
 *
 * Get its order backwards — defaults over the app's values rather than under them — and every primitive
 * in @repo/ui renders English under every locale, while the source stays exactly as the structural
 * guards in `accessible-names.test.ts` demand: the labels are declared, translated and wired. Nothing
 * static can tell the two spreads apart, and the symptom (English copy) is also what a correct English
 * render looks like.
 *
 * Testable here, unlike its consumers, because the provider is plain React — no Radix primitive, so the
 * duplicate-React problem the `testing` skill records does not apply.
 */

function Probe() {
  const labels = useUiLabels();
  return (
    <>
      <span data-testid="close">{labels.close}</span>
      <span data-testid="clear">{labels.clear}</span>
    </>
  );
}

describe('UiLabelsProvider', () => {
  it('prefers the app’s labels over the package defaults', () => {
    render(
      <UiLabelsProvider labels={{ close: 'Cerrar' }}>
        <Probe />
      </UiLabelsProvider>,
    );
    expect(screen.getByTestId('close')).toHaveTextContent('Cerrar');
  });

  it('falls back to a default for a label the app did not pass', () => {
    // Partial on purpose: a package that adds a label must keep rendering something until the app
    // translates it, rather than rendering nothing at all.
    render(
      <UiLabelsProvider labels={{ close: 'Cerrar' }}>
        <Probe />
      </UiLabelsProvider>,
    );
    expect(screen.getByTestId('clear')).toHaveTextContent(DEFAULT_UI_LABELS.clear);
  });

  it('renders the English defaults with no provider at all', () => {
    // The property that keeps @repo/ui usable on its own — a second app must not have to adopt this.
    render(<Probe />);
    expect(screen.getByTestId('close')).toHaveTextContent(DEFAULT_UI_LABELS.close);
  });
});
