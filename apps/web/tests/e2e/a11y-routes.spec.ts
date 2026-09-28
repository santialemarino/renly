import { A11Y_LOCALES, SIGNED_OUT_ROUTES, UNKNOWN_ROUTE } from './helpers/a11y-routes';
import { expect, expectNoA11yViolations, openForScan, scanName, test } from './helpers/axe';

/*
 * Every page a signed-out visitor can open, scanned by axe in both languages: the public pages, every
 * auth page in the state it renders with no token, the not-found page, and the auth FORMS a token
 * unlocks — which is what a real visitor arrives at from an email:
 *   * `/reset-password?token=…` renders the new-password form for any token (it is checked on submit);
 *   * `/signup?invite=…` renders the invited registration form only for a live invite, whose raw token
 *     the API never returns (only its hash is stored). CI seeds one in SQL and hands it over as
 *     `E2E_SIGNUP_INVITE_TOKEN`; without it — a local run — that one case skips, and CI refuses skips.
 * The live `/join` preview needs a token only a group admin can mint, so it is scanned from
 * `a11y-routes.auth.spec.ts`, in a signed-out context too. Zero tolerance — see `helpers/axe.ts` and
 * `helpers/a11y-allowlist.ts`.
 *
 * The route list comes from `config/routes.ts` through `helpers/a11y-routes.ts`, and
 * `tests/unit/a11y-sweep-coverage.test.ts` fails when a page exists that neither sweep scans.
 */

// eslint-disable-next-line turbo/no-undeclared-env-vars
const SIGNUP_INVITE_TOKEN = process.env.E2E_SIGNUP_INVITE_TOKEN;

const TOKEN_STATES: [string, string | null][] = [
  ['/reset-password (form)', '/reset-password?token=e2e-a11y-scan-only'],
  [
    '/signup (invited form)',
    SIGNUP_INVITE_TOKEN ? `/signup?invite=${encodeURIComponent(SIGNUP_INVITE_TOKEN)}` : null,
  ],
];

test.describe('accessibility sweep (signed out)', { tag: '@a11y' }, () => {
  for (const locale of A11Y_LOCALES) {
    for (const route of [...SIGNED_OUT_ROUTES, UNKNOWN_ROUTE]) {
      test(`${route} has no axe violations (${locale})`, async ({ page, makeAxeBuilder }, info) => {
        await openForScan(page, route, locale, { notFound: route === UNKNOWN_ROUTE });
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(route, locale), {
          wholePage: true,
        });
      });
    }

    for (const [name, url] of TOKEN_STATES) {
      test(`${name} has no axe violations (${locale})`, async ({ page, makeAxeBuilder }, info) => {
        test.skip(url === null, 'E2E_SIGNUP_INVITE_TOKEN is unset (CI seeds it)');
        await openForScan(page, url as string, locale);
        // Premise: the form is really there — the error screens these routes fall back to are
        // scanned above, and a scan of one of them here would be a duplicate under a false name.
        await expect(page.locator('input[type="password"]').first()).toBeVisible();
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(name, locale), {
          wholePage: true,
        });
      });
    }
  }
});
