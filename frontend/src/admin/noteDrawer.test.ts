// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { openNoteDrawer, type NoteDrawerOutcome } from './noteDrawer';

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
