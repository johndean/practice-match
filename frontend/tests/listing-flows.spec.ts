import { test, expect, type Page } from '@playwright/test';
import { crc32, deflateSync } from 'node:zlib';
import { appOrigin, guard, signInAs } from './harness';

// ---------------------------------------------------------------------------------------
// The seller's listing lifecycle, end to end, against the real API — controller amendment
// A-SL27 (5), the architectural fix of the SL7 fix loop.
//
// The four `wizard-*` states in `screens.ts` photograph the wizard at zero pixel tolerance, and
// they reach it through `prepare()`'s stubs: the oracle answers "Create a listing" with a fixed
// id and the design's own draft, so the frozen hashes hold whatever the API would have said.
// That is the right thing for a pixel oracle and the wrong thing for a product: THREE fix rounds
// passed every gate — pytest, vitest, the pixel oracle and the DOM oracle, all green — while a
// seller could not save a single wizard step, because every Continue put seventeen stray fields
// on the wire (CRITICAL-B), then the empty string where an enum was wanted (CRITICAL-C), and
// nothing anywhere pressed Continue against a real endpoint. This file is that press.
//
// Every assertion here is on what the API actually did: the status of the PATCH the design's own
// Continue sent, and the row `GET /api/seller/listings/{id}` returns afterwards — never the card,
// which can render a value the server refused. NOTHING is mocked, stubbed or intercepted: `guard`
// is `prepare()`'s error gate without its routes, the persona signs in through the real
// `/api/auth/signin`, and the listing this run creates is a real row the seller persona keeps.
//
// The trace goes off on a LIVE run and nowhere else, for the reason account-flows.spec.ts records
// (the persona's sign-in is out of band here, but the rule is one rule and
// `tests/playwright-config.test.ts` pins this line, its position, and the app project's testMatch).
// ---------------------------------------------------------------------------------------
test.use({ trace: process.env.PW_APP_URL ? 'off' : 'retain-on-failure' });


/** A wizard control by the label the design gives it. Substring, not exact: the design's `<label>`
 *  wraps the caption AND the help line under the field, so the control's accessible name carries
 *  both ("Practice name (staff-facing only) Never shown to buyers until…"). */
const field = (page: Page, label: string) => page.getByLabel(label);
const button = (page: Page, name: string) => page.getByRole('button', { name, exact: true });
/** A step-rail row — `screens.ts`'s own `btn(p, /^7/)`, the way the three rail captures press it. */
const rail = (page: Page, step: number) => page.getByRole('button', { name: new RegExp(`^${step}`) }).first();

/** The blurb the design shows under each step's title — unique to the step, unlike the title,
 *  which the rail repeats. */
const BLURB: Record<number, string> = {
  1: 'Start with what the practice is.',
  2: 'Buyers search by location.',
  3: 'Two numbers get a buyer to a decision.',
  4: 'The practical picture: who works there and what you do.',
  5: 'Real estate is usually the second question a buyer asks.',
  6: 'Photos do more than any other field to bring the right buyer to you.',
  7: 'You decide what an approved buyer sees before you have spoken to them.'
};
const onStep = (page: Page, step: number) => expect(page.getByText(BLURB[step])).toBeVisible();

/** `GET /api/seller/listings/{id}`, read from the page's own session — the row as the API serves
 *  it, not as the wizard renders it. */
async function draftOf(page: Page, id: string): Promise<Record<string, unknown> & { photos: { id: string; name: string }[]; assets: unknown[] }> {
  return page.evaluate((listingId) => fetch(`/api/seller/listings/${listingId}`, { credentials: 'same-origin' }).then((r) => r.json()), id);
}

/** Does `act`, which must make the wizard PATCH `step`, and requires that PATCH to be a 200 — the
 *  assertion three rounds never made — then reads the row back. */
async function saved(page: Page, id: string, step: number, act: () => Promise<void>) {
  const patch = page.waitForResponse((r) =>
    r.url().includes(`/api/seller/listings/${id}?step=${step}`) && r.request().method() === 'PATCH');
  await act();
  const response = await patch;
  expect(response.status(), `step ${step}'s PATCH: ${await response.text()}`).toBe(200);
  return draftOf(page, id);
}

/** The value beside a preview row's key (`previewRows`, logic.js) — the design's own two spans. */
const previewValue = (page: Page, key: string) =>
  page.locator(`div:has(> span > span:text-is("${key}"))`).locator('span.sc-interp').nth(1);

/** The first listing card on the dashboard. The API orders the seller's rows `updated_at DESC`,
 *  so the listing this run just wrote is always the first card. */
const firstRow = (page: Page) => page.locator('div[style*="var(--shadow-sm)"]').first();

/**
 * A real, decodable photograph — a 4 × 4 PNG built here rather than read from `seeds/`, so this
 * spec depends on no fixture file's continued existence. `app/media/encode.py` re-encodes it to
 * WebP; a broken image would be a 415 and fail the upload assertion below.
 */
function photograph(): Buffer {
  const width = 4;
  const height = 4;
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 3);
    row[0] = 0; // filter: none
    for (let x = 0; x < width; x++) row.set([0x33, 0x9d, 0xde], 1 + x * 3); // the design's own blue
    rows.push(row);
  }
  const chunk = (type: string, data: Buffer) => {
    const typeAndData = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(typeAndData));
    return Buffer.concat([length, typeAndData, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 2, 0, 0, 0], 8); // 8-bit, RGB, deflate, no filter method, no interlace
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0))
  ]);
}

const NAME = 'Flow Spec Animal Hospital';
const CAPTION = 'Front of the building, from the street';

test.describe('the seller listing lifecycle against the real API (A-SL27 (5))', () => {
  // -------------------------------------------------------------------------------------
  // One listing, from "Create a listing" to "In VIN Foundation review", through the design's own
  // controls and the real endpoints. It leaves that listing on the seller persona's dashboard —
  // the API has no delete for a listing, and an in-review row is exactly what SL8's admin half
  // needs to find in the queue.
  // -------------------------------------------------------------------------------------
  test('a seller creates a listing, fills every step and submits it for review', async ({ page }) => {
    guard(page);
    await signInAs(page, 'seller', '/seller');
    await expect(button(page, 'Create a listing')).toBeVisible();

    // 1. "Create a listing" CREATES one (A16.14): a real POST, a real row, the wizard on step 1.
    const created = page.waitForResponse((r) => r.url().endsWith('/api/seller/listings') && r.request().method() === 'POST');
    await button(page, 'Create a listing').click();
    const createdResponse = await created;
    expect(createdResponse.status(), 'the API minted the draft').toBe(201);
    const id = ((await createdResponse.json()) as { id: string }).id;
    await onStep(page, 1);
    expect(await draftOf(page, id), 'a bare draft: nothing typed, nothing chosen').toMatchObject({ id, status: 'draft', name: null, type: null, est: null });

    // 2. Step 1 through the design's own controls and Continue, the two selects left as the design
    //    opens them. The first PATCH of the first listing — the request that was a 400 for three
    //    rounds running — and the row it leaves holds the DESIGN's own defaults for the two enums
    //    the seller never touched (CRITICAL-C: a bare draft used to open on four blank selects and
    //    send "" for each).
    await field(page, 'Practice name').fill(NAME);
    await field(page, 'Year established').fill('1998');
    let row = await saved(page, id, 1, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ name: NAME, type: 'Small animal', est: 1998, ownership: 'Sole proprietor' });
    await onStep(page, 2);

    // 3. Step 2.
    await field(page, 'City or community').fill('Bastrop');
    await field(page, 'ZIP code').fill('78602');
    row = await saved(page, id, 2, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ city: 'Bastrop', zip: '78602', area: 'Bastrop', anon: true });
    await onStep(page, 3);

    // 4. "Save and exit" on step 3 with the asking price still BLANK (MAJOR-D). A draft is
    //    incomplete by nature: the save omits the blank required number instead of sending "",
    //    the API answers 200, and the seller is on the dashboard — not trapped behind
    //    `price must be a number`. Nothing already saved is lost.
    row = await saved(page, id, 3, () => button(page, 'Save and exit').click());
    expect(row).toMatchObject({ price: null, name: NAME, city: 'Bastrop', status: 'draft' });
    await expect(button(page, 'Create a listing'), 'back on the dashboard').toBeVisible();
    await expect(firstRow(page)).toContainText('Small animal practice — Bastrop');
    await expect(firstRow(page)).toContainText('Draft');

    // 5. "Continue" on the row re-opens THAT draft, hydrated from the API (A16.2/A16.17) — the
    //    assertion the wizard captures cannot make, since they open the design's stub. The two
    //    selects show what the API holds, which is what the design opened them on.
    await firstRow(page).getByRole('button', { name: 'Continue', exact: true }).click();
    await onStep(page, 1);
    await expect(field(page, 'Practice name')).toHaveValue(NAME);
    await expect(field(page, 'Practice type')).toHaveValue('Small animal');
    await expect(field(page, 'Current ownership')).toHaveValue('Sole proprietor');
    await expect(field(page, 'Year established')).toHaveValue('1998');

    // 6. The step rail SAVES the step it leaves before it moves (MAJOR-E, A16.18): change both
    //    selects on step 1, jump straight to step 3, and the changes are on the API.
    await field(page, 'Practice type').selectOption('Mixed');
    await field(page, 'Current ownership').selectOption('Two-doctor partnership');
    row = await saved(page, id, 1, () => rail(page, 3).click());
    expect(row).toMatchObject({ type: 'Mixed', ownership: 'Two-doctor partnership', name: NAME, est: 1998 });
    await onStep(page, 3);

    // 7. Step 3, now with both figures.
    await field(page, 'Asking price').fill('860,000');
    await field(page, 'Gross revenue, most recent year').fill('700,000');
    row = await saved(page, id, 3, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ price: 860000, rev: 700000 });
    await onStep(page, 4);

    // 8. Step 4.
    await field(page, 'Doctors (full-time equivalent)').fill('2');
    await field(page, 'Exam rooms').fill('4');
    await field(page, 'Approximate square feet').fill('3,000');
    await field(page, 'Hours').fill('Mon-Fri 8-6');
    await field(page, 'Services offered').fill('Wellness, dentistry, soft-tissue surgery');
    row = await saved(page, id, 4, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ docs: 2, rooms: 4, sqft: 3000, hours: 'Mon-Fri 8-6', desc: 'Wellness, dentistry, soft-tissue surgery' });
    await onStep(page, 5);

    // 9. Step 5 — the other two enum selects (CRITICAL-C's second half), one of them changed.
    await expect(field(page, 'Building status')).toHaveValue('Included');
    await expect(field(page, 'Facility type')).toHaveValue('Standalone');
    await field(page, 'Building status').selectOption('Leased');
    await field(page, 'Facility description').fill('Freestanding building on a corner lot.');
    row = await saved(page, id, 5, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ bldg: 'Leased', facilityType: 'Standalone', facility: 'Freestanding building on a corner lot.' });
    await onStep(page, 6);

    // 10. Step 6 without a photograph — the photograph is the next test's, where the API has a
    //     store to put it in. Its Continue writes nothing (there is no field to save) and advances.
    // Step 6's Continue writes nothing — its photograph is already stored — and advances.
    const nothingPatched: string[] = [];
    const watch = (r: import('@playwright/test').Request) => { if (r.method() === 'PATCH') nothingPatched.push(r.url()); };
    page.on('request', watch);
    await button(page, 'Continue').click();
    await onStep(page, 7);
    page.off('request', watch);
    expect(nothingPatched, 'step 6 has no fields to save').toEqual([]);

    // 11. Step 7: one disclosure switch flipped, saved by "Preview listing".
    await expect(field(page, 'Keep floor plans and financial packet locked')).toBeChecked();
    await field(page, 'Keep floor plans and financial packet locked').uncheck();
    row = await saved(page, id, 7, () => button(page, 'Preview listing').click());
    expect(row).toMatchObject({ docsLocked: false, anon: true });

    // 12. Step 8's preview is the truth about the draft: the typed values and the photograph.
    await expect(page.getByText('Preview — this is what an approved buyer sees')).toBeVisible();
    await expect(page.getByText('Mixed practice — Bastrop', { exact: true })).toBeVisible();
    await expect(previewValue(page, 'Established')).toHaveText('1998');
    await expect(previewValue(page, 'Asking price')).toHaveText('$860,000');
    await expect(previewValue(page, 'Doctors')).toHaveText('2');
    await expect(previewValue(page, 'Exam rooms')).toHaveText('4');
    await expect(previewValue(page, 'Square feet')).toHaveText('3,000');
    await expect(previewValue(page, 'Property')).toHaveText('Leased');
    await expect(previewValue(page, 'Photos attached')).toHaveText('0');

    // 13. Submit for review: a real POST, `in_review` on the API, the design's "Submitted" card.
    const submitted = page.waitForResponse((r) => r.url().endsWith(`/api/seller/listings/${id}/submit`) && r.request().method() === 'POST');
    await button(page, 'Submit for review').click();
    const submitResponse = await submitted;
    expect(submitResponse.status(), `Submit: ${await submitResponse.text()}`).toBe(200);
    await expect(page.getByText('Your listing is with the VIN Foundation')).toBeVisible();
    expect(await draftOf(page, id)).toMatchObject({ status: 'in_review', name: NAME, price: 860000 });

    // 14. …and the dashboard row says so, from the API's own row, once the wizard is left.
    await button(page, 'Save and exit').click();
    await expect(button(page, 'Create a listing')).toBeVisible();
    await expect(firstRow(page)).toContainText('Mixed practice — Bastrop');
    await expect(firstRow(page)).toContainText('$860K · 2 doctors · 3,000 sq ft');
    await expect(firstRow(page)).toContainText('In VIN Foundation review');
    await expect(firstRow(page)).toContainText('Submitted · awaiting VIN Foundation review');
  });

  // -------------------------------------------------------------------------------------
  // The photograph: one upload through the browser's own file dialog, described through the
  // browser's own prompt (A-SL20 — the approved step 6 has neither control), on a second draft
  // this run creates and leaves behind. Two real requests — the upload and the caption — and the
  // tile that appears is the caption, not a filename; the preview then counts it.
  //
  // Locally and in CI the api is `tests/e2e/api_under_test.py` (A-SL28), which holds an in-process
  // moto bucket, so the upload is real and this test never stands aside. A LIVE target may have no
  // bucket: it is asked, out of band, and the answer is quoted.
  // -------------------------------------------------------------------------------------
  test('a seller adds a photograph with a caption, and the preview counts it', async ({ page }) => {
    guard(page);
    await signInAs(page, 'seller', '/seller');

    const created = page.waitForResponse((r) => r.url().endsWith('/api/seller/listings') && r.request().method() === 'POST');
    await button(page, 'Create a listing').click();
    const id = ((await (await created).json()) as { id: string }).id;
    await onStep(page, 1);

    if (process.env.PW_APP_URL) {
      // The upload route checks for its store BEFORE it reads the file (`upload_photo`), so a
      // bodiless POST is answered `503 STORAGE_UNAVAILABLE` by a target with no bucket and with a
      // 4xx about the missing file by one that has it — nothing is uploaded either way. Out of band
      // (`page.request`, the context's own cookies) so a 503 never reaches the console gate, with
      // the double-submit token and Origin the API requires of every write.
      const csrf = (await page.context().cookies()).find((c) => c.name === 'pm_csrf');
      const probe = await page.request.post(`/api/seller/listings/${id}/photos`, { headers: { 'X-CSRF-Token': csrf!.value, Origin: appOrigin() } });
      const answer = await probe.text();
      test.skip(probe.status() === 503, `the live target answered 503 ${answer} — it has no object store, so the photograph is proven where a bucket exists (A-SL28 (2))`);
    }

    // Straight to step 6 by the rail: the rail saves step 1 first (A16.18, partial mode — the
    // blank year is left out) and that save is a 200 on a draft nobody has typed into.
    await saved(page, id, 1, () => rail(page, 6).click());
    await onStep(page, 6);

    page.once('dialog', (dialog) => { void dialog.accept(CAPTION); });
    const chooser = page.waitForEvent('filechooser');
    const uploaded = page.waitForResponse((r) => r.url().endsWith(`/api/seller/listings/${id}/photos`) && r.request().method() === 'POST');
    const captioned = page.waitForResponse((r) => r.url().includes(`/api/seller/listings/${id}/assets/`) && r.request().method() === 'PATCH');
    await button(page, 'Add files').click();
    await (await chooser).setFiles({ name: 'exterior.png', mimeType: 'image/png', buffer: photograph() });
    const uploadResponse = await uploaded;
    expect(uploadResponse.status(), `the upload: ${await uploadResponse.text()}`).toBe(201);
    const captionResponse = await captioned;
    expect(captionResponse.status(), `the caption PATCH: ${await captionResponse.text()}`).toBe(200);
    await expect(page.getByText(CAPTION, { exact: true })).toBeVisible();
    const row = await draftOf(page, id);
    expect(row.photos.map((p) => p.name), 'one photograph, in the seller\'s own words').toEqual([CAPTION]);
    expect(row.assets).toHaveLength(1);

    // The preview counts it — the row the design's A16.12 reads photographs, not files, from.
    await rail(page, 8).click();
    await expect(page.getByText('Preview — this is what an approved buyer sees')).toBeVisible();
    await expect(previewValue(page, 'Photos attached')).toHaveText('1');
  });
});
