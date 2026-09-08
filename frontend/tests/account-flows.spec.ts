import { test, expect, type Browser, type Page } from '@playwright/test';
import {
  DECLINED_FIELDS, NEEDS_REVIEW_INFO_REQUEST, NOTICES, PERSONAS, PERSONA_DEFAULT_PASSWORD, PERSONA_INVITE_PASSWORD,
  appOrigin, expectApiStatus, nextFixtureToken, nextThrowawayEmail, prepare, reach, settleExpectedApiFailures,
  signInAs, booted
} from './harness';

// ---------------------------------------------------------------------------------------
// The account lifecycle, end to end, against the real API — spec §6's "the app reaches each
// through real routes and real API calls" and §8's acceptance, once per run.
//
// The fifteen approved states in `screens.ts` photograph the OUTCOMES of these flows at zero
// pixel tolerance. That proves the screens are the design's; it does not prove the product
// produced them, because a screenshot of a card cannot tell a real 202 from a card the harness
// posed. This file is the other half: every assertion here is on what the API actually did — the
// status of the response, the row `GET /api/applications/me` returns, whether the new password
// signs in — and none of it is mocked, stubbed or intercepted.
//
// The trace goes off on a LIVE run and nowhere else, for the reason signin-form.spec.ts records:
// these tests type passwords into the design's own cards, a failing run's trace carries them, and
// CI publishes `frontend/test-results`. Locally and in CI those passwords are the documented
// test-only constants; the one run where a password is a real secret is a live one.
// `tests/playwright-config.test.ts` pins this line, its position, and the app project's testMatch.
// ---------------------------------------------------------------------------------------
test.use({ trace: process.env.PW_APP_URL ? 'off' : 'retain-on-failure' });

const email = (page: Page) => page.getByLabel('Email', { exact: true });
const password = (page: Page) => page.getByLabel('Password', { exact: true });
const button = (page: Page, name: string) => page.getByRole('button', { name, exact: true });

/** `GET /api/applications/me`, read from the page's own session — the applicant's row as the API
 *  serves it, not as the card renders it. */
async function applicationsMe(page: Page): Promise<{ current: Record<string, unknown> | null; history: unknown[] }> {
  return page.evaluate(() => fetch('/api/applications/me', { credentials: 'same-origin' }).then((r) => r.json()));
}

/**
 * The reviewer's half of the loop, and the reason it is here at all.
 *
 * `POST /api/applications` and `POST /api/applications/{id}/answer` both move the ACCOUNT to
 * `pending` (app/api/applications.py) — so the two flows below consume the very fixture states
 * `gate-answer`, `gate-reapply` and `gate-declined` are captured from, and Playwright runs this
 * file before `dom.spec.ts` and `visual.spec.ts`. Putting the applicant back is therefore not
 * housekeeping but a correctness requirement, and the honest way to do it is the way the product
 * does it: a reviewer decides. `request_info` and `decline` are exactly the transitions spec §8
 * asks for ("staff can request information, the applicant answers and re-submits, is declined,
 * re-applies"), so restoring the fixture and proving the staff side are one action.
 *
 * Neither action ends the target's sessions (`ENDS_EVERY_SESSION` is suspend and revoke alone), so
 * the applicant's memoised jar survives and no sign-in is spent putting it back.
 */
async function decideAs(browser: Browser, accountId: string, action: 'request_info' | 'decline', note: string): Promise<void> {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await signInAs(page, 'design');
    const csrf = (await context.cookies()).find((c) => c.name === 'pm_csrf');
    expect(csrf, 'the admin session carries the double-submit token the API requires').toBeTruthy();
    const response = await page.request.post(`/api/admin/users/${accountId}/decide`, {
      // `deps.check_origin_and_csrf` compares the header against the jar and `Origin` against the
      // URL it posts to — a page-derived request context sends neither on its own.
      headers: { 'X-CSRF-Token': csrf!.value, Origin: appOrigin() },
      data: { action, note }
    });
    expect(response.status(), await response.text()).toBe(200);
  } finally {
    await context.close();
  }
}

test.describe('the account lifecycle against the real API (spec §6/§8)', () => {
  // -------------------------------------------------------------------------------------
  // 1. Sign up, and ask for a reset on the same address. ONE of `SIGNUP_IP`'s five per hour and
  // one of `FORGOT_IP`'s ten, on an address RFC 2606 reserves and nothing can deliver to.
  // -------------------------------------------------------------------------------------
  test('a stranger signs up, is told to check their email, and can ask for a reset link', async ({ page }) => {
    await prepare(page);
    const address = nextThrowawayEmail('signup');

    await page.goto('/signup');
    await expect(page.getByText('Start with the email and password you will sign in with.')).toBeVisible();
    await email(page).fill(address);
    await password(page).fill(PERSONA_DEFAULT_PASSWORD);
    const signup = page.waitForResponse((r) => r.url().endsWith('/api/auth/signup') && r.request().method() === 'POST');
    await button(page, 'Create account').click();
    expect((await signup).status(), 'the API accepted the sign-up').toBe(202);

    // Spec §3 row 2, verbatim — including the address the API was actually given.
    await expect(page.getByText('Check your email')).toBeVisible();
    await expect(page.getByText(
      `We sent a verification link to ${address}. It is valid for 24 hours. Open it to confirm your address, then sign in to complete your access request.`
    )).toBeVisible();
    await expect(page.getByText('24 hours', { exact: true }), 'the card\'s "Link valid for" row').toBeVisible();

    // …and the same address through the forgot card (spec §3 row 4). The API answers 202 whether
    // or not it will send anything — this one is still `unverified`, which `forgot` excludes on
    // purpose — and the card says the same either way, which is the point of a uniform response.
    await page.goto('/forgot');
    await expect(page.getByText('We will email you a link.')).toBeVisible();
    await email(page).fill(address);
    const forgot = page.waitForResponse((r) => r.url().endsWith('/api/auth/password/forgot') && r.request().method() === 'POST');
    await button(page, 'Send reset link').click();
    expect((await forgot).status()).toBe(202);
    await expect(page.getByText(NOTICES['reset-sent'])).toBeVisible();
  });

  // -------------------------------------------------------------------------------------
  // 2. A verification link works once. The second visit is the REAL 400 the expired card is made
  // of — `expectApiStatus` allows exactly that one console line and then asserts it happened.
  // -------------------------------------------------------------------------------------
  test('a verification link confirms the address once, and is dead the second time', async ({ page }) => {
    await prepare(page);
    const token = nextFixtureToken('verify');

    await page.goto(`/verify?token=${token}`);
    await expect(page.getByText(NOTICES.verified)).toBeVisible();
    // Spec S3: the token is read once and the history entry replaced, so it never survives in a
    // URL the app wrote. `stateToRoute` maps the sign-in card the verify landed on to `/`, so that
    // is where the settle leaves it — with no query at all, which is the property that matters.
    expect(new URL(page.url()).search, 'no token survives in the address bar').toBe('');
    await expect(page).toHaveURL(/\/$/);

    expectApiStatus(page, 400);
    await page.goto(`/verify?token=${token}`);
    await expect(page.getByText('This link is no longer valid')).toBeVisible();
    await expect(page.getByText('Verification links work once and expire after 24 hours. Request a new one with the same email and password.')).toBeVisible();
    await settleExpectedApiFailures(page);
  });

  // -------------------------------------------------------------------------------------
  // 3. A reset link sets a new password, and the new password is what the account now has.
  // -------------------------------------------------------------------------------------
  test('a reset link changes the password, and the new one signs the account in', async ({ page }) => {
    await prepare(page);
    await booted(page);
    // The same flow `gate-signin-password-updated` is captured from: a seeded reset token, two
    // matching passwords, the design's own card. `reach` records the rotation, because the API
    // revoked every session this account had and changed the credential the run holds for it.
    await reach(page, { gate: 'signin', notice: 'password-updated' });
    await expect(page.getByText(NOTICES['password-updated'])).toBeVisible();

    // The proof: the NEW password opens the account. Out of band, in a request context of its own
    // — which is what keeps it out of the browser trace (A-I7).
    const context = await page.context().browser()!.newContext();
    try {
      const fresh = await context.newPage();
      await signInAs(fresh, 'verified');
      expect(
        await fresh.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json())),
        'the session belongs to the account the reset token was issued for'
      ).toMatchObject({ email: PERSONAS.verified.email, state: 'verified' });
    } finally {
      await context.close();
    }
  });

  // -------------------------------------------------------------------------------------
  // 4. An invitation sets the FIRST password on an account that had no usable one.
  // -------------------------------------------------------------------------------------
  test('an invitation link sets the first password, and the invited account then signs in', async ({ page }) => {
    await prepare(page);
    await booted(page);
    await reach(page, { gate: 'signin', notice: 'invite-set' });
    await expect(page.getByText(NOTICES['invite-set'])).toBeVisible();

    const context = await page.context().browser()!.newContext();
    try {
      const fresh = await context.newPage();
      // `signInAs` reaches `personaCredentials('invited')`, which throws until the run has set a
      // password on this account — so getting here at all is half the assertion.
      await signInAs(fresh, 'invited');
      expect(await fresh.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json())))
        .toMatchObject({ email: PERSONAS.invited.email });
    } finally {
      await context.close();
    }
  });

  // -------------------------------------------------------------------------------------
  // 5. The applicant answers the reviewer's question and re-submits (spec §3 row 7).
  // -------------------------------------------------------------------------------------
  test('an applicant under review answers the question and is back under review', async ({ page, browser }) => {
    await prepare(page);
    await signInAs(page, 'needsReview');
    const me = await page.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json()));

    // The card's sub-line is the reviewer's own question, fetched — not a fixture string.
    await expect(page.getByText('More information requested')).toBeVisible();
    await expect(page.getByText(NEEDS_REVIEW_INFO_REQUEST)).toBeVisible();
    expect((await applicationsMe(page)).current).toMatchObject({ status: 'needs_review', info_request: NEEDS_REVIEW_INFO_REQUEST });

    const answer = 'I am an associate at Hill Country Veterinary Clinic and see small animals four days a week.';
    await page.getByLabel('Your answer', { exact: true }).fill(answer);
    await button(page, 'Re-submit request').click();

    await expect(page.getByText('Your request is under review')).toBeVisible();
    expect((await applicationsMe(page)).current, 'the answer reached the row, and the row is open again')
      .toMatchObject({ status: 'pending', answer });

    // Put the fixture back the way the product does — see `decideAs`.
    await decideAs(browser, String(me.id), 'request_info', NEEDS_REVIEW_INFO_REQUEST);
    expect((await applicationsMe(page)).current).toMatchObject({ status: 'needs_review', info_request: NEEDS_REVIEW_INFO_REQUEST });
  });

  // -------------------------------------------------------------------------------------
  // 6. The declined applicant re-applies (spec §3, "Re-apply needs no new screen").
  //
  // This is where the pre-fill is PROVEN: `gate-reapply`'s screenshot types the seeded values into
  // both targets (A-S5 ruling 2, because the reference has no API to fetch them from), so the only
  // place the app's own pre-fill is asserted is here — before anything is typed.
  // -------------------------------------------------------------------------------------
  test('a declined applicant re-applies from their own last answers, and the request is open again', async ({ page, browser }) => {
    await prepare(page);
    await signInAs(page, 'declined');
    const me = await page.evaluate(() => fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json()));

    await expect(page.getByText('Access was not granted')).toBeVisible();
    const before = await applicationsMe(page);
    expect(before.current).toMatchObject({ status: 'declined' });
    expect(before.current!.fields, 'the API serves the applicant their own answers (A-S4)').toMatchObject(DECLINED_FIELDS);

    await page.getByRole('button', { name: 'Reply with more information', exact: true }).click();

    // PRE-FILLED, before this test touches a field: the assertion the screenshot state cannot make.
    for (const [label, value] of [
      ['Full name and credentials', DECLINED_FIELDS.name],
      ['Veterinary school and graduation year', DECLINED_FIELDS.school_year],
      ['License state', DECLINED_FIELDS.license_state],
      ['Current practice or employer', DECLINED_FIELDS.employer],
      ['Why do you want access?', DECLINED_FIELDS.intent]
    ] as const) {
      await expect(page.getByLabel(label, { exact: true }), label).toHaveValue(value);
    }
    await expect(page.getByRole('checkbox').first(), 'the affirmation they made last time').toBeChecked();

    const submitted = page.waitForResponse((r) => r.url().endsWith('/api/applications') && r.request().method() === 'POST');
    await button(page, 'Submit request').click();
    expect((await submitted).status()).toBe(202);
    await expect(page.getByText('Your request is under review')).toBeVisible();

    const after = await applicationsMe(page);
    expect(after.current, 'a NEW row, open, carrying the answers they re-submitted').toMatchObject({ status: 'pending' });
    expect(after.current!.id, 'the declined row was not edited — a second application exists').not.toBe(before.current!.id);
    expect(after.current!.fields).toMatchObject(DECLINED_FIELDS);

    // …and the reviewer declines it again, which is both spec §8's next step and what puts the
    // fixture back for `gate-declined` and `gate-reapply`.
    await decideAs(browser, String(me.id), 'decline', 'Employer is outside the marketplace\'s current pilot region.');
    expect((await applicationsMe(page)).current).toMatchObject({ status: 'declined' });
  });

  // -------------------------------------------------------------------------------------
  // 7. A member refused a route their access does not include (spec §3 row 8).
  // -------------------------------------------------------------------------------------
  test('a buyer deep-linking /admin is told the page is not available to their account', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'buyer', '/admin');

    await expect(page.getByText('This page is not available to your account')).toBeVisible();
    await expect(page.getByText(
      'Your approved access does not include this page. If you think it should, write to the VIN Foundation from the address on your account.'
    )).toBeVisible();
    // The status card's two buttons: the state's own primary, and the design's fixed secondary.
    await expect(button(page, 'Back to Browse Practices')).toBeVisible();
    await expect(button(page, 'Sign out')).toBeVisible();
    // The refusal is the ROUTER's, not the API's: the session is real and Admin simply is not in
    // this account's grants, so nothing 4xx'd and no console error was logged.
    await expect(page.getByText('Dr. Rachel Mendes').first()).toBeVisible();

    await button(page, 'Back to Browse Practices').click();
    await expect(page).toHaveURL(/\/browse$/);
  });

  // -------------------------------------------------------------------------------------
  // 8. "Send it again" for an account that arrived here by SIGNING IN (A-S4.1).
  //
  // The card's primary has two branches: it re-posts the sign-up when the visitor still holds the
  // password they typed, and calls `POST /api/auth/verify/resend` — which needs none, only the
  // session — when they do not. Before that endpoint existed this branch posted an EMPTY password,
  // the uniform 202 answered, and the card claimed to have sent a link that was never issued. The
  // assertion is therefore on the response itself: which endpoint answered, and with what.
  // -------------------------------------------------------------------------------------
  test('"Send it again" really re-sends for an unverified account that signed in', async ({ page }) => {
    await prepare(page);
    await signInAs(page, 'unverified');

    await expect(page.getByText('Check your email')).toBeVisible();
    await expect(page.getByText(`Sent to`)).toBeVisible();
    await expect(page.getByText(PERSONAS.unverified.email).first()).toBeVisible();

    const resend = page.waitForResponse((r) => r.url().endsWith('/api/auth/verify/resend') && r.request().method() === 'POST');
    await button(page, 'Send it again').click();
    const response = await resend;
    expect(response.status(), 'the session-authenticated resend, not a sign-up with an empty password').toBe(202);
    expect(await response.json()).toEqual({ status: 'check_email' });
  });
});
