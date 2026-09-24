/**
 * The disclosure-capability vocabulary, in the product's own voice — ONE home for the five names a
 * seller releases and the words a member reads for them.
 *
 * App-only code the reference never receives (`frontend/src/requests/buyer.ts`'s own position,
 * A52's ruling), so it carries no amendment. `LEVEL_LABEL` LIVED in `frontend/src/admin/requests.ts`
 * (A56) and is MOVED here rather than copied, under ruling D-C67 (John, 2026-09-24: "all toggles
 * must be fully functional and SELLER must be able to manage it all and per seller"), which gave it
 * a second reader: the seller's own chooser. That module re-exports it, so nothing that already
 * imported it from there has to change, and a second spelling of any of these words cannot appear
 * — CLAUDE.md's own A16.23/A40 lesson, one vocabulary over.
 */

/** `app.disclosure.levels.CAPABILITIES`, in the order this product states them everywhere else
 *  (`app/disclosure/levels.py`, `migrations/097_request_approved_capabilities.sql`'s own CHECK,
 *  the directive's §16 list). A set has no order of its own, so a stable one has to be declared
 *  somewhere or a seller would read their own choices back in whatever order they ticked them. */
export const CAPABILITY_ORDER: readonly string[] = [
  'IDENTITY', 'EXACT_LOCATION', 'UNREDACTED_IMAGES', 'FINANCIALS', 'FLOOR_PLANS'
];

/** `app.disclosure.levels.REQUESTABLE_LEVELS`, pinned by equality in
 *  `frontend/src/admin/requests.test.ts`. Title case, the design's own vocabulary register (its
 *  fixture rows read "Small animal", "Emergency", never a shouted enum). */
export const LEVEL_LABEL: Record<string, string> = {
  IDENTITY: 'Identity',
  EXACT_LOCATION: 'Exact location',
  UNREDACTED_IMAGES: 'Unredacted images',
  FINANCIALS: 'Financials',
  FLOOR_PLANS: 'Floor plans',
  FULL_CONFIDENTIAL: 'Full confidential'
};

/** The five, in declared order, as a chooser's own rows — `{ value, label }`, which is what
 *  `openChoiceDrawer` takes. No help line per row: this product names these five in exactly one
 *  voice and inventing a sentence about each of them is what D-C67's own brief forbids. */
export function capabilityOptions(): { value: string; label: string }[] {
  // No `?? value` fallback, and that is measured rather than optimistic: every member of
  // `CAPABILITY_ORDER` is a `LEVEL_LABEL` key, which `capabilities.test.ts` pins, so the fallback
  // would be a branch no test could reach honestly — the bundle's own rule is to delete such a
  // branch rather than defend a state the data forbids.
  return CAPABILITY_ORDER.map((value) => ({ value, label: LEVEL_LABEL[value] }));
}

/** The capabilities `values` holds, in declared order and with anything this build has never heard
 *  of dropped — `app.disclosure.levels.granted`'s own per-member rule, client side, so a name added
 *  to the API before it is added here reads as "not shown" rather than as a shouted enum in a
 *  sentence a seller is meant to trust. */
export function orderedCapabilities(values: readonly string[] | null | undefined): string[] {
  if (!values) return [];
  return CAPABILITY_ORDER.filter((name) => values.includes(name));
}

/** "financials and floor plans" — the released set as a phrase, for the seller's own inbox row.
 *  Empty for an empty set: the caller says what "nothing" reads as, because the sentence around it
 *  is not the same sentence. */
export function capabilityPhrase(values: readonly string[] | null | undefined): string {
  // `orderedCapabilities` answers only `CAPABILITY_ORDER` members, every one of which is a
  // `LEVEL_LABEL` key — see `capabilityOptions` above for why there is no fallback here either.
  const words = orderedCapabilities(values).map((name) => LEVEL_LABEL[name].toLowerCase());
  if (words.length === 0) return '';
  if (words.length === 1) return words[0];
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}
