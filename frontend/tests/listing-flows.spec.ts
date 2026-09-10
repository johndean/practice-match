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
async function draftOf(page: Page, id: string): Promise<Record<string, unknown> & {
  photos: { id: string; name: string; source: 'seed' | 'asset'; position?: number }[]; assets: unknown[];
}> {
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

    // 9. Step 5 — the other two enum selects (CRITICAL-C's second half), one of them changed — left
    //    by the wizard's own BACK button (MAJOR-F, A16.19): Back saves the step it leaves exactly as
    //    the rail does, so the typed step 5 is on the API before step 4 shows.
    await expect(field(page, 'Building status')).toHaveValue('Included');
    await expect(field(page, 'Facility type')).toHaveValue('Standalone');
    await field(page, 'Building status').selectOption('Leased');
    await field(page, 'Facility description').fill('Freestanding building on a corner lot.');
    row = await saved(page, id, 5, () => button(page, 'Back').click());
    expect(row).toMatchObject({ bldg: 'Leased', facilityType: 'Standalone', facility: 'Freestanding building on a corner lot.' });
    await onStep(page, 4);
    // …and forward again through Continue, the typed values still in the form.
    await saved(page, id, 4, () => button(page, 'Continue').click());
    await onStep(page, 5);
    await expect(field(page, 'Building status')).toHaveValue('Leased');
    row = await saved(page, id, 5, () => button(page, 'Continue').click());
    expect(row).toMatchObject({ bldg: 'Leased', facility: 'Freestanding building on a corner lot.' });
    await onStep(page, 6);

    // 10. Step 6 without a photograph — the photograph is the next test's, where the API has a
    //     store to put it in. Its Continue writes nothing (there is no field to save) and advances.
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

  // -------------------------------------------------------------------------------------
  // Click-to-caption for an EXISTING photograph — A-SL25 (10) / Task SL7b. All 195 seeded
  // photographs carry only their SEED inventory caption until a seller clicks the tile and
  // re-describes it; `caption()` (the asset route) has no uuid to match a seed path against, so
  // this exercises the NEW positional route, `PATCH /api/seller/listings/{id}/photos/{n}`.
  //
  // The eighteen demo hospitals are a GLOBAL guarantee, not this test's own side effect —
  // `scripts/seed_listings.py` joins `targets.ts`'s LOCAL `api` web server chain and
  // `global-setup.ts::reseedRemoteFixtures`'s REMOTE one, right beside `seed_persona.py`, so the
  // seller persona (`SEED_OWNER_EMAIL`, the same `seller@practice-match.test` `signInAs` signs in
  // as) owns every hospital before any test runs, on EITHER target — no skip, the same "runs for
  // real everywhere" rule the photograph test's own probe-based skip is the sole exception to.
  //
  // `4444_denver_veterinary_specialist_hospital` is identified by its own SLUG (`serialise_draft`
  // answers it verbatim), never by city or type alone, and chosen DELIBERATELY among the eighteen
  // (A-SL32 (3), on the SL7b re-review): its stored `ownership`, "Three-doctor LLC", is OUTSIDE the
  // wizard's own four-option vocabulary — the same register as fifteen of the eighteen — and the
  // step rail this test presses PATCHes step 1's whole `w` (A16.18) to leave it. Before A-SL31 this
  // was refused (`400 ownership must be one of …`) for a value the seller never typed; `abc_animal_
  // hospital`'s "Sole proprietor" was chosen instead precisely because it dodged that defect, which
  // the re-review named as the second time on this branch that a convenient fixture concealed a
  // real failure. `columns_for` now skips the vocabulary check for an enum the incoming PATCH does
  // not change, so this hospital's own prose survives a step it never touched — proved here, not
  // routed around.
  //
  // The seeder is idempotent but a re-caption is not undone by re-seeding a CLAIMED row (A-SL21:
  // `WHERE listing.source = 'seed'` leaves an edited row alone), so a second run of this suite
  // finds the SAME row already carrying a PREVIOUS run's caption — nothing here asserts what the
  // caption WAS, only what this run's own write leaves it as, and the tile is found by its
  // POSITION in the DOM (the first of step 6's tiles), never by caption text.
  // -------------------------------------------------------------------------------------
  test('a seller re-describes a seeded photograph by clicking its tile', async ({ page }) => {
    guard(page);
    await signInAs(page, 'seller', '/seller');

    const mine = await page.evaluate(() =>
      fetch('/api/seller/listings?limit=200', { credentials: 'same-origin' }).then((r) => r.json())) as
      { items: { id: string; slug: string | null }[] };
    const seeded = mine.items.find((item) => item.slug === '4444_denver_veterinary_specialist_hospital');
    if (!seeded) throw new Error('scripts/seed_listings.py did not seed 4444_denver_veterinary_specialist_hospital for the seller persona');
    const id = seeded.id;

    const before = await draftOf(page, id);
    expect(before.photos[0], 'position 1 is this hospital\'s own first photograph — a SEED entry, all eighteen filled')
      .toMatchObject({ source: 'seed', position: 1 });

    // The dashboard's own card for this listing — found by its title and price together, since
    // the id is not in the DOM to select by.
    const card = page.locator('div[style*="var(--shadow-sm)"]')
      .filter({ hasText: 'Specialty practice — Denver' }).filter({ hasText: '$2.74M' });
    await card.getByRole('button', { name: 'Edit', exact: true }).click();
    await onStep(page, 1);

    await saved(page, id, 1, () => rail(page, 6).click());
    await onStep(page, 6);

    // The FIRST tile — position 1 — by its place in the DOM, not by its (possibly already
    // rewritten, by an earlier run of this very test) caption.
    const tile = page.locator('div[style*="width: 92px"]').first();
    const NEW_CAPTION = 'Freshly repainted entrance, photographed this spring';
    page.once('dialog', (dialog) => { void dialog.accept(NEW_CAPTION); });
    const described = page.waitForResponse((r) =>
      r.url().endsWith(`/api/seller/listings/${id}/photos/1`) && r.request().method() === 'PATCH');
    await tile.click();
    const describedResponse = await described;
    expect(describedResponse.status(), `the positional caption PATCH: ${await describedResponse.text()}`).toBe(200);
    await expect(page.getByText(NEW_CAPTION, { exact: true })).toBeVisible();

    const after = await draftOf(page, id);
    expect(after.photos[0]).toMatchObject({ name: NEW_CAPTION, source: 'seed', position: 1 });
    // The claim (A-SL21): the row is the seller's own, source flipped, the moment they touch it.
    expect(after.status, 're-describing a photograph is an edit and re-enters review').toBe('in_review');
  });

  // -------------------------------------------------------------------------------------
  // Task SL8's seeded-listing assertion: Edit on one of the eighteen shows THAT hospital's own
  // seeded values — never the design's fixture ones, and never a dash where a real figure exists.
  // `abc_animal_hospital` is picked by its own SLUG: its ownership ("Sole proprietor") and every
  // other enum are already in the wizard's own vocabulary, so this test is about what the fields
  // SHOW, not about A-SL31's fix (SL7b's re-describe-photo test, above, exercises a hospital whose
  // ownership is not, for that reason).
  //
  // Every step's rail press SAVES the step it leaves (A16.18) — on a PUBLISHED listing that is an
  // edit, so this run also re-enters this hospital into review, exactly as the photograph test
  // above does to its own. Accepted and precedented, not incidental: the seeder's `WHERE source =
  // 'seed'` scope (A-SL21) leaves a claimed row alone from here on.
  // -------------------------------------------------------------------------------------
  test('Edit on a seeded hospital shows its own seeded values, not the design\'s fixture ones', async ({ page }) => {
    guard(page);
    await signInAs(page, 'seller', '/seller');

    const mine = await page.evaluate(() =>
      fetch('/api/seller/listings?limit=200', { credentials: 'same-origin' }).then((r) => r.json())) as
      { items: { id: string; slug: string | null }[] };
    const seeded = mine.items.find((item) => item.slug === 'abc_animal_hospital');
    if (!seeded) throw new Error('scripts/seed_listings.py did not seed abc_animal_hospital for the seller persona');
    const id = seeded.id;

    const card = page.locator('div[style*="var(--shadow-sm)"]')
      .filter({ hasText: 'Small animal practice — Houston' }).filter({ hasText: '$465K' });
    await card.getByRole('button', { name: 'Edit', exact: true }).click();
    await onStep(page, 1);

    // Step 1: name, type and year — the seller's own prose, not "Hill Country Animal Hospital".
    await expect(field(page, 'Practice name')).toHaveValue('ABC Animal Hospital');
    await expect(field(page, 'Practice type')).toHaveValue('Small animal');
    await expect(field(page, 'Year established')).toHaveValue('1987');
    let row = await saved(page, id, 1, () => rail(page, 2).click());
    expect(row).toMatchObject({ name: 'ABC Animal Hospital', type: 'Small animal', est: 1987 });

    // Step 2: city and ZIP.
    await onStep(page, 2);
    await expect(field(page, 'City or community')).toHaveValue('Houston');
    await expect(field(page, 'ZIP code')).toHaveValue('77076');
    row = await saved(page, id, 2, () => rail(page, 3).click());
    expect(row).toMatchObject({ city: 'Houston', zip: '77076' });

    // Step 3: price and revenue.
    await onStep(page, 3);
    await expect(field(page, 'Asking price')).toHaveValue('465000');
    await expect(field(page, 'Gross revenue, most recent year')).toHaveValue('950000');
    row = await saved(page, id, 3, () => rail(page, 4).click());
    expect(row).toMatchObject({ price: 465000, rev: 950000 });

    // Step 4: doctors, exam rooms, square feet.
    await onStep(page, 4);
    await expect(field(page, 'Doctors (full-time equivalent)')).toHaveValue('1');
    await expect(field(page, 'Exam rooms')).toHaveValue('3');
    await expect(field(page, 'Approximate square feet')).toHaveValue('2400');
    row = await saved(page, id, 4, () => rail(page, 5).click());
    expect(row).toMatchObject({ docs: 1, rooms: 3, sqft: 2400 });

    // Step 5: property status — the design's own word for the seeded column value ("Separate"
    // reads as "Available separately", `BLDG_OUT`).
    await onStep(page, 5);
    await expect(field(page, 'Building status')).toHaveValue('Available separately');
    row = await saved(page, id, 5, () => rail(page, 6).click());
    expect(row).toMatchObject({ bldg: 'Available separately' });

    // Step 6: the hospital's own photographs, listed BY CAPTION — never a filename, never the
    // design's fixed slot names (A-SL20).
    await onStep(page, 6);
    await expect(page.getByText('Exterior — front', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Interior — reception', { exact: true }).first()).toBeVisible();

    // Step 8: the preview shows the real figures, never the design's em dash.
    await rail(page, 8).click();
    await expect(page.getByText('Preview — this is what an approved buyer sees')).toBeVisible();
    await expect(page.getByText('Small animal practice — Houston', { exact: true })).toBeVisible();
    await expect(previewValue(page, 'General location')).toHaveText('Houston, TX');
    await expect(previewValue(page, 'Established')).toHaveText('1987');
    await expect(previewValue(page, 'Asking price')).toHaveText('$465000');
    await expect(previewValue(page, 'Gross revenue')).toHaveText('$950000');
    await expect(previewValue(page, 'Doctors')).toHaveText('1');
    await expect(previewValue(page, 'Exam rooms')).toHaveText('3');
    await expect(previewValue(page, 'Square feet')).toHaveText('2400');
    await expect(previewValue(page, 'Property')).toHaveText('Available separately');
    // ...and every one of the eighteen photographs, not the design's fixed three.
    await expect(previewValue(page, 'Photos attached')).toHaveText('18');
  });

  // -------------------------------------------------------------------------------------
  // Task SL8's own deliverable, A-SL24 (2): sign in as the design persona, Admin › Listings shows
  // the real queue — the listing this run just submitted, never one of the design's five fixture
  // rows (D24) — decide it THROUGH THE UI (the browser's own prompts standing in for state and
  // market, D12, `admin/listings.ts`'s `windowUi`), and the seller's dashboard reflects it. Every
  // assertion is on the API's own rows, never on a card, which can render a value the server
  // refused.
  // -------------------------------------------------------------------------------------
  test('admin decides the seller\'s submitted listing, and the seller\'s dashboard reflects it', async ({ page, browser }) => {
    guard(page);
    await signInAs(page, 'seller', '/seller');

    const ADMIN_NAME = 'Flow Spec Admin Decision Hospital';
    // A city unique to this RUN, not merely this test: the admin queue is real, shared data on a
    // local dev database nothing here resets between runs (the documented hazard), and the queue
    // is searched by its title (type + city) in a SEPARATE session below — a repeated local run
    // must not find a PRIOR run's own leftover "Kyle" instead of (or alongside) this run's.
    const CITY = `Kyle${Date.now()}`;
    const created = page.waitForResponse((r) => r.url().endsWith('/api/seller/listings') && r.request().method() === 'POST');
    await button(page, 'Create a listing').click();
    const id = ((await (await created).json()) as { id: string }).id;
    await onStep(page, 1);

    await field(page, 'Practice name').fill(ADMIN_NAME);
    await field(page, 'Year established').fill('1999');
    await saved(page, id, 1, () => button(page, 'Continue').click());
    await onStep(page, 2);
    await field(page, 'City or community').fill(CITY);
    await field(page, 'ZIP code').fill('78640');
    await saved(page, id, 2, () => button(page, 'Continue').click());
    await onStep(page, 3);
    await field(page, 'Asking price').fill('700,000');
    await field(page, 'Gross revenue, most recent year').fill('900,000');
    await saved(page, id, 3, () => button(page, 'Continue').click());
    // Step 4: `listing_submittable_ck` needs only name/city/zip/type/est/price, but this listing
    // is about to be PUBLISHED for real, onto the real Browse feed the last assertion below reads
    // — and the approved design's own Browse card computes `p.sqft.toLocaleString()`
    // unconditionally (logic.js:1714), so a published listing with no square footage crashes
    // every screen's next render, not merely its own. A seller who has reached the preview has
    // filled this step in every other flow this spec drives; this one does too.
    await onStep(page, 4);
    await field(page, 'Doctors (full-time equivalent)').fill('2');
    await field(page, 'Exam rooms').fill('4');
    await field(page, 'Approximate square feet').fill('3,000');
    await saved(page, id, 4, () => rail(page, 8).click());
    // Step 8 is the preview — it has no rail blurb of its own (`BLURB` covers steps 1-7 only, the
    // FIRST test's own convention), so it is found by its own heading instead.
    await expect(page.getByText('Preview — this is what an approved buyer sees')).toBeVisible();
    const submitted = page.waitForResponse((r) => r.url().endsWith(`/api/seller/listings/${id}/submit`) && r.request().method() === 'POST');
    await button(page, 'Submit for review').click();
    expect((await submitted).status()).toBe(200);
    expect((await draftOf(page, id)).status).toBe('in_review');

    // The reviewer's own session — a second context, exactly `account-flows.spec.ts`'s
    // `decideAs` shape — signed in as `design@`, staff and admin among its roles.
    const adminContext = await browser.newContext();
    try {
      const adminPage = await adminContext.newPage();
      guard(adminPage);
      await signInAs(adminPage, 'design', '/admin?tab=listings');

      // The real queue (D24): the row this run just submitted, found by its own title and price
      // together — the Admin Listing cell shows the design's own computed title (type + city),
      // never the seller's staff-only "Practice name" (D9's `serialise_draft` distinction) — never
      // one of the design's five literal fixture rows, whichever the API answered. `display: grid`
      // rather than the row's own `grid-template-columns` value: Chromium re-serialises a style
      // attribute's numbers on the way back out (`.8fr` becomes `0.8fr`), which a substring match
      // on the source literal would miss.
      const row = adminPage.locator('div[style*="display: grid"]')
        .filter({ hasText: `Small animal practice — ${CITY}` }).filter({ hasText: '$700K' });
      await expect(row).toBeVisible();
      await expect(row).toContainText('In review');

      // Publish, through the UI: the browser's own two prompts for state and market (D12,
      // `needsFields`), asked because this listing has never been published before.
      // Chained, not both registered up front: two `.once('dialog', ...)` calls made before
      // either prompt appears both attach to the FIRST dialog event (Node's EventEmitter has no
      // notion of "the next one, then the one after"), so the second handler raced the first for
      // the very same dialog and lost. Registering the second only once the first has fired
      // targets it at the SECOND prompt, which is the one it is for.
      adminPage.once('dialog', (dialog) => {
        void dialog.accept('TX');
        adminPage.once('dialog', (dialog2) => { void dialog2.accept('Austin, TX'); });
      });
      const decided = adminPage.waitForResponse((r) =>
        r.url().endsWith(`/api/admin/listings/${id}/decide`) && r.request().method() === 'POST');
      await row.getByRole('button', { name: 'Publish', exact: true }).click();
      const decidedResponse = await decided;
      expect(decidedResponse.status(), `the decide POST: ${await decidedResponse.text()}`).toBe(200);
      const decidedBody = await decidedResponse.json() as { status: string; state: string; market: string };
      expect(decidedBody).toMatchObject({ status: 'published', state: 'TX', market: 'Austin, TX' });
    } finally {
      await adminContext.close();
    }

    // …and the seller's own dashboard reflects the decision — read from the API, not the card.
    expect(await draftOf(page, id)).toMatchObject({ status: 'published', state: 'TX', market: 'Austin, TX' });
    const onTheMarket = await page.evaluate(() =>
      fetch('/api/listings', { credentials: 'same-origin' }).then((r) => r.json())) as { items: { id: string }[] };
    expect(onTheMarket.items.map((item) => item.id), 'a publish reaches Browse at once (D16)').toContain(id);
  });
  // -------------------------------------------------------------------------------------
  // Task B10, A-C31 (4) — "The test that proves it is an end-to-end one, not a unit test."
  //
  // Every unit test in this repository was green while the docked panel read "0" Population,
  // "0.0% (5 yrs)", "$0K" Median Income and "Flat" Population Growth for a listing the Census
  // has no figures for, because no unit test ever RENDERED the panel against such a listing and
  // the pixel oracle only ever sees the design's own fixtures, which all have figures. This one
  // does: it runs against the real API and the eighteen seeded hospitals, whose `market_metric`
  // rows this environment does not have — so the panel it opens is exactly the D-C31 case.
  //
  // The precondition is read from the API and ASSERTED, not assumed and not skipped on: a
  // vacuous pass is exactly how this defect survived three rounds. If a later task materialises
  // Census rows for every seeded Austin hospital, this fails and says why, and whoever does that
  // work points it at a listing that still has none.
  // -------------------------------------------------------------------------------------
  test('the docked panel fabricates nothing for a listing the Census cannot describe (A-C31 (4))', async ({ page }) => {
    guard(page);
    // The seller persona carries the `buyer` role too, and its cookies are already memoised by
    // the tests above, so this costs the run no extra sign-in (harness.ts, THE BUDGET).
    await signInAs(page, 'seller', '/browse');

    // Browse opens on the design's default metro, and the results rail lists that metro's
    // published listings. Take one the API serves with no community figures at all.
    const listings = await page.evaluate(() =>
      fetch('/api/listings?limit=200', { credentials: 'same-origin' }).then((r) => r.json())) as {
        items: { id: string; area: string; market: string; pop: string | null; hh: string | null;
                 income: string | null; growth: string | null; vets: number | null;
                 econ_k: number | null; community_label: string | null }[] };
    const blank = listings.items.filter((i) =>
      i.market === 'Austin, TX' && i.pop === null && i.hh === null && i.income === null
      && i.growth === null && i.vets === null && i.econ_k === null && i.community_label === null);
    expect(blank.length, 'this case needs an Austin listing the API serves with NO community figures; every one of them now has some')
      .toBeGreaterThan(0);

    // Open its card in the results rail. The rail shows the area under the practice name.
    await page.getByText(blank[0].area, { exact: true }).first().click();
    const panel = page.locator('div.rf-scroll[style*="width: 366px"]');
    await panel.getByRole('button', { name: 'View full listing' }).waitFor({ state: 'visible' });

    // D-C31, at the only place that can see it: the rendered panel.
    const text = (await panel.innerText()).replace(/\s+/g, ' ');
    for (const banned of ['undefined', 'NaN', '$0K', '0.0%', 'Flat', 'Lean', 'Median', 'Challenging']) {
      expect(text, `the docked panel renders "${banned}" for a listing with no community figures`)
        .not.toContain(banned);
    }
    // …and a bar drawn at its floor is a reading, not an absence: the competition row's three
    // bars and the score ring's conic gradient are not in the DOM at all.
    await expect(panel.getByText('Veterinary Establishments')).toHaveCount(0);
    await expect(panel.locator('[style*="conic-gradient"]')).toHaveCount(0);

    // A-C31 (2): it shows the design's OWN unavailable treatment, and still offers the listing.
    await expect(panel.getByText('Community data unavailable for this location')).toBeVisible();
    await expect(panel.getByText('The Census geography for this address has not been matched yet.')).toBeVisible();
    await expect(panel.getByRole('button', { name: 'View full listing' })).toBeVisible();

    // …and the detail behind it says the same thing rather than a grid of blanks.
    await panel.getByRole('button', { name: 'View full listing' }).click();
    await expect(page.getByText('Community data unavailable for this location')).toBeVisible();
  });
});
