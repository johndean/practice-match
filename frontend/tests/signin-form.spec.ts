import { test, expect, type Page } from '@playwright/test';
import { PERSONAS, isExpectedSignInFailure401, personaCredentials, prepare } from './harness';

// ---------------------------------------------------------------------------------------
// The trace goes off on a LIVE run and nowhere else (round 3, ruling 1).
//
// These three tests type a password into the design's own sign-in card, so a FAILING run's trace
// carries it — and CI publishes `frontend/test-results`. In every local and CI run that password is
// the documented test-only default, so a trace there discloses nothing; the one run where it is a
// real secret is a live one (`PW_APP_URL` set — the QA hand-back, with `PERSONA_PASSWORD` from the
// operator's Keychain, never Railway, A-S6.2). When `PW_APP_URL` is unset this resolves to the
// project's own `retain-on-failure`, so nothing changes locally or in CI, and the TESTS are never
// skipped: the form is precisely what
// Task I10 has to prove on QA.
//
// This is why they live in a FILE of their own rather than a describe inside smoke.spec.ts:
// Playwright refuses `use({ trace })` inside a describe group — "because it forces a new worker" —
// and allows it at the top level of a file. Round 2 put it at the top of smoke.spec.ts, which cost
// the WHOLE smoke suite its traces on a live run; a file of its own scopes it to these three.
// `tests/playwright-config.test.ts` pins the line, its position, and the app project's testMatch.
// ---------------------------------------------------------------------------------------
test.use({ trace: process.env.PW_APP_URL ? 'off' : 'retain-on-failure' });

/** Collects console and page errors for an end-of-test assertion, where `prepare()` throws at
 *  once — the wrong-password case below deliberately provokes a 401 and needs to say so. */
function trapErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  return errors;
}

// ---------------------------------------------------------------------------------------
// The design's OWN sign-in form, end to end (review round 1, I2).
//
// Commit 2's whole user-visible behaviour — amendments A5.1 and A5.3, the `auth` adapter — had no
// end-to-end coverage: every other test signs in out of band with `signInAs`, which sets cookies
// and reloads, so `main.ts`'s load-before-mount populated the store and the interactive path was
// never exercised. That is exactly what hid review round 1's C1: the adapter resolved with the
// `Me` but never wrote it to the store, so after typing credentials into the form the member was
// signed in as far as `logic.js` was concerned and anonymous as far as `guard()` was concerned,
// and the next navigation bounced them to the empty `unavailable` gate.
//
// These three run against the REAL API through Vite's `/api` proxy, in their own anonymous
// contexts — they never touch `signInAs`, so the per-persona memo other tests share is untouched
// and the sessions they open are their own.
//
// Budget: three of `SIGNIN_IP`'s thirty attempts per 15 minutes, and one of `SIGNIN_EMAIL`'s ten
// failures for `buyer@` (the deliberate wrong password). See harness.ts's memo docstring for the
// run's full arithmetic.
//
// NOTE, and it is a real one: typing a password into a form necessarily puts it in the Playwright
// trace of a FAILING run, which CI publishes. A-I7 went out of its way to keep the persona
// credential out of traces (a standalone request context; the reauth check signed out from
// outside the browser). Testing the design's own form as ruled cannot preserve that, so the
// documented test-only constant is now reachable from a failed run's artifacts — flagged to the
// controller rather than quietly traded away.
// ---------------------------------------------------------------------------------------
test.describe('the design\'s own sign-in form, against the real API (A5.1/A5.3, I2)', () => {
  const email = (page: Page) => page.getByLabel('Email', { exact: true });
  const password = (page: Page) => page.getByLabel('Password', { exact: true });
  /** The sign-in CARD's body — the innermost div holding the password field, which is the design's
   *  own `flex-direction: column` block with the two labels, the error box and the submit button.
   *  Scoped, because the site header carries a second "Sign in" button for a signed-out visitor
   *  (`goSignInScreen`, V3:102) and an unscoped exact-name lookup is a strict-mode violation. */
  const card = (page: Page) => page.locator('div').filter({ has: page.getByLabel('Password', { exact: true }) }).last();
  const signInButton = (page: Page) => card(page).getByRole('button', { name: 'Sign in', exact: true });

  async function typeCredentials(page: Page, persona: 'buyer', pw: string) {
    await email(page).fill(PERSONAS[persona].email);
    await password(page).fill(pw);
    await signInButton(page).click();
  }

  test('buyer credentials sign the member in, the header shows who they are, and a member route opens', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await expect(page.getByText('Approved members only')).toBeVisible();

    await typeCredentials(page, 'buyer', personaCredentials('buyer').password);

    // A5.1 lands on Browse, and A5.4's header strings come from `/api/me` — not from the design's
    // fixture, which for this account happens to read identically (A-I8.2 chose it for that).
    await expect(page).toHaveURL(/\/browse$/);
    await expect(page.getByRole('button', { name: /^Layers/ })).toBeVisible();
    await expect(page.getByText('Dr. Rachel Mendes').first()).toBeVisible();
    await expect(page.getByText('Approved buyer · StartUp Club').first()).toBeVisible();

    // C1's actual symptom: the store has to hold the principal by now, or `guard()` refuses the
    // next member route and this lands on the empty `unavailable` gate instead of My Requests.
    await page.getByRole('button', { name: 'My Requests', exact: true }).first().click();
    await expect(page).toHaveURL(/\/requests$/);
    await expect(page.getByText('My Requests').first()).toBeVisible();
    expect(await page.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.status)), 'the session is real').toBe(200);
  });

  test('a wrong password shows the server\'s own message and leaves the visitor on the gate', async ({ page }) => {
    // `prepare()` is deliberately NOT used here: a refused sign-in IS a 401, Chromium logs every
    // 4xx subresource as a console error that cannot be suppressed, and `prepare()`'s gate turns
    // any console error into a failure. `trapErrors` collects instead, and the assertion below
    // says exactly which errors this test expects — one, the refusal it asked for.
    const errors = trapErrors(page);
    await page.goto('/');

    await typeCredentials(page, 'buyer', 'definitely-not-the-password');

    // The API's own wording (`app/api/auth.py`'s InvalidCredentials), rendered in the card's error
    // box — the design's `{{ form.errorText }}`. A5.1 passes the server's prose through rather
    // than inventing copy, because 401 and 429 want different words on the same form.
    await expect(page.getByText('Email or password is incorrect.')).toBeVisible();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText('Approved members only')).toBeVisible();
    await expect(signInButton(page), 'still on the sign-in card, not signed in anywhere').toBeVisible();
    expect(await page.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.status)), 'no session was created').toBe(401);

    expect(
      errors.filter((e) => !isExpectedSignInFailure401(e)),
      'the only console error this test expects is the 401 it deliberately provoked'
    ).toEqual([]);
  });

  test('signing out from the account menu returns to the gate, and a member route no longer opens', async ({ page }) => {
    await prepare(page);
    await page.goto('/');
    await typeCredentials(page, 'buyer', personaCredentials('buyer').password);
    await expect(page).toHaveURL(/\/browse$/);

    // The design's own account menu: the identity button opens it, "Sign out" is inside.
    await page.getByRole('button', { name: /Dr\. Rachel Mendes/ }).first().click();
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText('Approved members only')).toBeVisible();

    // A5.3 ended the real session, and the adapter cleared the store with it — so a fresh load of
    // a member route is an anonymous visit, gate and all. `pm_csrf` goes with the session, which
    // is why this reload asks `/api/me` nothing and logs no 401 (me.ts, A-I8.2).
    await page.goto('/browse');
    await expect(page.getByText('Approved members only')).toBeVisible();
    await expect(page.getByRole('button', { name: /^Layers/ }), 'Browse must not render for a signed-out visitor').toHaveCount(0);
  });
});
