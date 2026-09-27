import { A11Y_LOCALES, SIGNED_OUT_ROUTES, UNKNOWN_ROUTE } from './helpers/a11y-routes';
import { expectNoA11yViolations, openForScan, scanName, test } from './helpers/axe';

/*
 * Every page a signed-out visitor can open, scanned by axe in both languages: the public pages, every
 * auth page in the state it renders with no token, and the not-found page. Zero tolerance — see
 * `helpers/axe.ts` for the preset and `helpers/a11y-allowlist.ts` for the only way an exception gets in.
 *
 * The route list comes from `config/routes.ts` through `helpers/a11y-routes.ts`, and
 * `tests/unit/a11y-sweep-coverage.test.ts` fails when a page exists that neither sweep scans. The
 * signed-in half is `a11y-routes.auth.spec.ts`.
 */
test.describe('accessibility sweep (signed out)', { tag: '@a11y' }, () => {
  for (const locale of A11Y_LOCALES) {
    for (const route of [...SIGNED_OUT_ROUTES, UNKNOWN_ROUTE]) {
      test(`${route} has no axe violations (${locale})`, async ({ page, makeAxeBuilder }, info) => {
        await openForScan(page, route, locale);
        const results = await makeAxeBuilder().analyze();
        await expectNoA11yViolations(page, results, info, scanName(route, locale), {
          wholePage: true,
        });
      });
    }
  }
});
