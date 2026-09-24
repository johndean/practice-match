// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { openConfirmDrawer, openNoteDrawer, type NoteDrawerOutcome } from './noteDrawer';

afterEach(() => {
  document.body.innerHTML = '';
});

function query<T extends Element>(selector: string): T {
  const el = document.querySelector(selector);
  if (el === null) throw new Error(`not found: ${selector}`);
  return el as T;
}

/** The primary button, by its own label — never "the first `<button>`", which is the close
 *  button (the interest modal's own three-button shape: close, primary, secondary). */
function submitButton(label = 'Decline'): HTMLButtonElement {
  const found = [...document.querySelectorAll('button')].find((b) => b.textContent === label);
  if (found === undefined) throw new Error(`no button labelled ${label}`);
  return found as HTMLButtonElement;
}

function cancelButton(): HTMLButtonElement {
  return submitButton('Cancel');
}

function config(overrides: Partial<Parameters<typeof openNoteDrawer>[0]> = {}) {
  return {
    title: 'Decline',
    subtitle: 'Dr. Priya Raghavan',
    label: 'Why is this account being declined?',
    submitLabel: 'Decline',
    maxLength: 4000,
    submit: vi.fn<(note: string) => Promise<NoteDrawerOutcome>>().mockResolvedValue({ ok: true }),
    ...overrides
  };
}

describe('openNoteDrawer', () => {
  it('renders the composed drawer with the caller\'s own title, subtitle, label and submit label', () => {
    void openNoteDrawer(config());
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    expect(query('[role="dialog"]').getAttribute('aria-modal')).toBe('true');
    // The interest modal's own three-button shape: close (icon only, no text), primary, secondary.
    const labels = [...document.querySelectorAll('button')].map((b) => b.textContent);
    expect(labels).toEqual(['', 'Decline', 'Cancel']);
    expect(document.body.textContent).toContain('Dr. Priya Raghavan');
    expect(document.body.textContent).toContain('Why is this account being declined?');
  });

  it('bounds the field to the caller\'s own MAX_NOTE, never a value invented here', () => {
    void openNoteDrawer(config({ maxLength: 123 }));
    expect(query<HTMLTextAreaElement>('textarea').maxLength).toBe(123);
  });

  it('focuses the field on open', () => {
    void openNoteDrawer(config());
    expect(document.activeElement).toBe(query('textarea'));
  });

  it('disables the primary button until the field carries non-blank text', () => {
    void openNoteDrawer(config());
    const textarea = query<HTMLTextAreaElement>('textarea');
    const submit = submitButton();
    expect(submit.disabled).toBe(true);

    textarea.value = '   ';
    textarea.dispatchEvent(new Event('input'));
    expect(submit.disabled).toBe(true);

    textarea.value = 'a real reason';
    textarea.dispatchEvent(new Event('input'));
    expect(submit.disabled).toBe(false);
  });

  it('submits the typed note, and resolves once the decision lands', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>().mockResolvedValue({ ok: true });
    const done = openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    textarea.value = 'affiliation could not be verified';
    textarea.dispatchEvent(new Event('input'));
    submitButton().click();
    expect(submit).toHaveBeenCalledWith('affiliation could not be verified');
    await done;
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('keeps the note and shows the refusal in its own error slot, rather than losing what was typed', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>()
      .mockResolvedValueOnce({ ok: false, message: 'cannot decline an account in state active' });
    void openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    textarea.value = 'a reviewer note';
    textarea.dispatchEvent(new Event('input'));
    submitButton().click();
    // The microtasks the submit promise resolves on.
    await Promise.resolve();
    await Promise.resolve();

    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    expect(textarea.value).toBe('a reviewer note');
    expect(document.body.textContent).toContain('cannot decline an account in state active');
    expect(submitButton().disabled).toBe(false);
  });

  it('lets the reviewer retry after a refusal, and resolves once the retry lands', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>()
      .mockResolvedValueOnce({ ok: false, message: 'cannot decline an account in state active' })
      .mockResolvedValueOnce({ ok: true });
    const done = openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    textarea.value = 'a reviewer note';
    textarea.dispatchEvent(new Event('input'));
    submitButton().click();
    await Promise.resolve();
    await Promise.resolve();

    submitButton().click();       // the SAME text, retried
    expect(submit).toHaveBeenLastCalledWith('a reviewer note');
    await done;
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('disables the controls while a submit is in flight, so a second click cannot double-submit', async () => {
    let resolveSubmit: (o: NoteDrawerOutcome) => void = () => {};
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>()
      .mockReturnValue(new Promise((resolve) => { resolveSubmit = resolve; }));
    void openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    const submitBtn = submitButton();
    const cancelBtn = cancelButton();
    textarea.value = 'a reviewer note';
    textarea.dispatchEvent(new Event('input'));
    submitBtn.click();
    submitBtn.click();          // ignored — one call only
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submitBtn.disabled).toBe(true);
    expect(cancelBtn.disabled).toBe(true);
    expect(textarea.disabled).toBe(true);
    resolveSubmit({ ok: true });
    await Promise.resolve();
  });

  it('resolves without submitting when the reviewer cancels', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>();
    const done = openNoteDrawer(config({ submit }));
    cancelButton().click();
    await done;
    expect(submit).not.toHaveBeenCalled();
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('cancels on the close button, exactly as the Cancel button does', async () => {
    const done = openNoteDrawer(config());
    query<HTMLButtonElement>('[aria-label="Close"]').click();
    await done;
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('cancels on Escape', async () => {
    const done = openNoteDrawer(config());
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await done;
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('cancels on a click outside the box, and not on a click inside it', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>();
    const done = openNoteDrawer(config({ submit }));
    const box = query<HTMLDivElement>('[role="dialog"]');
    const scrim = box.parentElement as HTMLDivElement;
    box.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(1);   // still open
    scrim.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    await done;
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(0);
  });

  it('returns focus to the element that opened it', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const done = openNoteDrawer(config());
    query<HTMLButtonElement>('[aria-label="Close"]').click();
    await done;
    expect(document.activeElement).toBe(opener);
  });

  it('does not throw returning focus when the active element is not an HTMLElement', async () => {
    // `Element#focus` is an `HTMLOrSVGElement` mixin method, not `Element`'s own, and
    // `document.activeElement` is typed `Element | null` — an SVG element (real in a document that
    // embeds one) or a foreign element focused via `tabindex` can be it, and neither one is an
    // `HTMLElement`. `close()`'s own guard is exactly this instance check.
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    document.body.appendChild(svg);
    const spy = vi.spyOn(document, 'activeElement', 'get').mockReturnValue(svg);
    const done = openNoteDrawer(config());
    cancelButton().click();
    await done;
    spy.mockRestore();
  });

  it('ignores a cancel while a submit is in flight — the close button and Escape are not disabled', async () => {
    let resolveSubmit: (o: NoteDrawerOutcome) => void = () => {};
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>()
      .mockReturnValue(new Promise((resolve) => { resolveSubmit = resolve; }));
    const done = openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    textarea.value = 'a reviewer note';
    textarea.dispatchEvent(new Event('input'));
    submitButton().click();

    // The close (X) icon stays clickable while busy (only the two text buttons and the field are
    // disabled) and Escape is a document-level listener with no busy check of its own — both must
    // still be safe no-ops rather than abandon a decision already in flight.
    query<HTMLButtonElement>('[aria-label="Close"]').click();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(document.body.querySelectorAll('[role="dialog"]')).toHaveLength(1);

    resolveSubmit({ ok: true });
    await done;
  });

  it('never submits a blank note, even reached directly rather than through the disabled button', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>();
    void openNoteDrawer(config({ submit }));
    // The button is disabled while the field is blank, which already stops a real click; this
    // reaches the handler the one other way a disabled control's listener still fires — a
    // dispatched event rather than the element's own `.click()` — so the guard inside is proved
    // rather than merely implied by the disabled attribute.
    submitButton().dispatchEvent(new MouseEvent('click'));
    expect(submit).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------------------
  // Task 7 (findings U1/U2): the step-6 tile's own describe surface reuses this drawer, and it
  // asks for something a DECISION never does — a caller may need the field's blank to MEAN
  // something. `caption_asset` treats blank and null as one intent, "the seller is taking the
  // description back", so a drawer that can never submit an empty field would take that away.
  // -------------------------------------------------------------------------------------
  it('allowEmpty lets a blank field submit, so a caller whose blank MEANS something can take it', async () => {
    const c = config({ allowEmpty: true, submitLabel: 'Save description' });
    const done = openNoteDrawer(c);
    expect(submitButton('Save description').disabled).toBe(false);
    submitButton('Save description').click();
    await done;
    expect(c.submit).toHaveBeenCalledWith('');
  });

  it('a caller with no subtitle draws no subtitle element, rather than an empty one', () => {
    const { subtitle: _drop, ...rest } = config();
    openNoteDrawer(rest);
    expect(query('[role="dialog"]').textContent).not.toContain('Dr. Priya Raghavan');
    expect([...query('[role="dialog"]').querySelectorAll('div')]
      .filter((d) => d.getAttribute('style')?.includes('margin-top: 3px'))).toEqual([]);
  });

  it('falls back to a generic message when a refusal names none', async () => {
    const submit = vi.fn<(note: string) => Promise<NoteDrawerOutcome>>().mockResolvedValueOnce({ ok: false });
    void openNoteDrawer(config({ submit }));
    const textarea = query<HTMLTextAreaElement>('textarea');
    textarea.value = 'a reviewer note';
    textarea.dispatchEvent(new Event('input'));
    submitButton().click();
    await Promise.resolve();
    await Promise.resolve();
    expect(document.body.textContent).toContain('That decision could not be recorded.');
  });
});

/**
 * Task 7 fix round (John's ruling, 2026-09-24: Remove must ask before it destroys). A seller who
 * misclicks loses an uploaded photograph permanently, and photographs are the field the design
 * itself says do more than any other to bring the right buyer — so the same drawer, in its
 * confirm-shaped variant, stands in front of the delete. Composed from the interest modal's own
 * SENT branch, which is already exactly this shape: one sentence in a padded body above a
 * primary-and-secondary button row.
 */
describe('openConfirmDrawer', () => {
  function confirm(overrides: Partial<Parameters<typeof openConfirmDrawer>[0]> = {}) {
    return {
      title: 'Remove this photograph',
      subtitle: 'The front door',
      body: 'This photograph is removed from the listing and cannot be brought back.',
      confirmLabel: 'Remove',
      ...overrides
    };
  }

  it('names what is being destroyed — the kind in its title, the seller\'s own words beneath it', () => {
    void openConfirmDrawer(confirm());
    const dialog = query('[role="dialog"]');
    expect(dialog.textContent).toContain('Remove this photograph');
    expect(dialog.textContent).toContain('The front door');
    expect(dialog.textContent).toContain('cannot be brought back');
    // Never a field: this drawer asks nothing, it only confirms.
    expect(dialog.querySelector('textarea')).toBeNull();
  });

  it('puts the SAFE action on the secondary button and the destructive one on the primary', () => {
    void openConfirmDrawer(confirm());
    // The interest modal's own pair: the primary is the `flex: 1` blue one, the secondary the
    // bordered white one. The safe choice is the secondary, which is the ruling.
    expect(submitButton('Remove').getAttribute('style')).toContain('background: var(--color-blue)');
    expect(cancelButton().getAttribute('style')).toContain('border: 1px solid var(--border-subtle)');
  });

  it('focuses the SAFE action on open, never the destructive one (fix round 2, Important-1)', () => {
    // A keyboard seller presses Enter on a tile's Remove button: keydown -> click -> this drawer
    // opens, all inside ONE keystroke. If the destructive primary took focus, the OS's own
    // auto-repeat (~500 ms) would fire a second keydown straight onto it and the photograph would
    // be gone without the dialog ever having been read. John's ruling — "the SAFE action is the
    // secondary button" — has to hold for the KEYBOARD and not only for the layout.
    void openConfirmDrawer(confirm());
    expect(document.activeElement).toBe(cancelButton());
    expect(document.activeElement).not.toBe(submitButton('Remove'));
  });

  it('resolves true only when the destructive button is pressed', async () => {
    const answered = openConfirmDrawer(confirm());
    submitButton('Remove').click();
    expect(await answered).toBe(true);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it.each([
    ['Cancel', () => cancelButton().click()],
    ['the close button', () => query<HTMLButtonElement>('button[aria-label="Close"]').click()],
    ['Escape', () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))]
  ])('resolves false on %s, so a misclick destroys nothing', async (_name, dismiss) => {
    const answered = openConfirmDrawer(confirm());
    dismiss();
    expect(await answered).toBe(false);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it('resolves false on a click outside the box, and not on one inside it', async () => {
    const answered = openConfirmDrawer(confirm());
    query('[role="dialog"]').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    const scrim = query('[role="dialog"]').parentElement!;
    scrim.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    expect(await answered).toBe(false);
  });

  it('an EMPTY subtitle draws no element either, not a blank line (fix round 2, Important-2)', () => {
    // `shell()`'s own docstring says an empty element is the thing it exists to avoid, and `''`
    // is not `undefined`, so the `!== undefined` test let one through. The design's own `sc-if`
    // idiom is TRUTHINESS (`sc-if value="{{ u.pill }}"` becomes `v-if="u?.pill"`), which is what
    // this now matches — defence in depth beside the caller fix, since a caller with nothing to
    // name is a caller with nothing to name however it spells it.
    openConfirmDrawer(confirm({ subtitle: '' })).catch(() => undefined);
    // The heading is the header's own first child — title, then the subtitle when there is one.
    // Selected explicitly rather than by `querySelector('div')`, which finds the HEADER and whose
    // second child is the close button: that reads as a blank line and is not one.
    const heading = query('[role="dialog"] > div > div');
    expect([...heading.children].map((c) => c.textContent)).toEqual(['Remove this photograph']);
  });

  it('a caller with no subtitle draws no subtitle element here either', () => {
    const { subtitle: _drop, ...rest } = confirm();
    void openConfirmDrawer(rest);
    expect(query('[role="dialog"]').textContent).not.toContain('The front door');
  });

  it('returns focus to the element that opened it', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const answered = openConfirmDrawer(confirm());
    cancelButton().click();
    await answered;
    expect(document.activeElement).toBe(opener);
  });

  it('does not throw returning focus when the active element is not an HTMLElement', async () => {
    // `openNoteDrawer`'s own case, one surface over: `document.activeElement` is typed
    // `Element | null` and an SVG element can be it, which has no `focus()` of `Element`'s own.
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    document.body.appendChild(svg);
    const spy = vi.spyOn(document, 'activeElement', 'get').mockReturnValue(svg);
    const answered = openConfirmDrawer(confirm());
    [...document.querySelectorAll('button')].find((b) => b.textContent === 'Cancel')!.click();
    expect(await answered).toBe(false);
    spy.mockRestore();
  });
});
