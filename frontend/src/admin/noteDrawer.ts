/**
 * The real decision drawer ruling D-C60 asks for (John, 2026-09-21, verbatim: "The VIN Foundation
 * Admin should have the option to request further information from applciation and or add
 * detailed explanation of the rejection"), replacing `window.prompt` — one line, no way to keep
 * text across a refusal, and no error surface of its own
 * (`docs/superpowers/specs/2026-09-21-admin-decision-notes-ruling.md`).
 *
 * COMPOSED FROM V3'S OWN ELEMENTS, never invented, the `admin/users.ts` `cell()`/`A()` idiom of
 * copying the design's own style strings VERBATIM rather than through the amendment engine — this
 * surface is app-only glue the reference never renders, `frontend/src/requests/buyer.ts`'s own
 * position, so it carries no amendment. The outer shell — scrim, box, title, 30 px close button,
 * the primary/secondary button pair and the error slot — is the INTEREST MODAL's own declarations
 * (`Practice Match V3.dc.html`'s `interestOpen` block: the scrim's `rgba(0,58,112,.55)` at
 * `z-index: 900`, the box's `max-width: 520px`, the header's `var(--rf-band)` band, the close
 * button's `delete-x.svg` and the `modal.error` slot's `#f5f5f5` band with a `var(--vf-text)`
 * left border). The FIELD itself — the label-plus-textarea pair — is the APPLICANT-ANSWER gate
 * card's (`gateAnswer`'s own `answerForm.text` label and textarea), the closer stylistic match:
 * that card, like this drawer, presents ONE field directly inside a padded body with no "shared
 * summary" box above it, which is what the interest modal's own textarea sits under.
 *
 * THE NOTE SURVIVES A REFUSAL (gap 2 of the spec's five): `submit` is called with the CURRENT
 * text, and a `{ ok: false }` outcome is shown in the error slot with the textarea's value left
 * exactly as the reviewer typed it — never cleared, never re-prompted from blank. The drawer is
 * the ONE place a decision for a NOTE_REQUIRED action is attempted, so a submit that lands closes
 * it and a submit that is refused keeps it open for a retry or a cancel.
 *
 * THE LENGTH BOUND is the caller's own `maxLength` (`admin/users.ts`'s `MAX_NOTE`, pinned against
 * `app/api/admin_users.py`'s own constant by `tests/test_docs.py`) — set as the textarea's real
 * HTML `maxlength`, so the browser itself refuses the keystroke that would cross it rather than
 * this surface discovering it only after the server's `INVALID_REQUEST` 422, which
 * (`app/auth/deps.py`) never reflects the length back for a caller to explain.
 */

export interface NoteDrawerOutcome {
  ok: boolean;
  message?: string;
}

export interface NoteDrawerConfig {
  /** The drawer's own title — the action's own label ("Decline", "Request info", "Suspend"), so
   *  the drawer reads the same word as the button that opened it. */
  title: string;
  /** Who the decision is about, under the title, the interest modal's own `modal.sub` idiom. */
  subtitle: string;
  /** The field's own label — the exact question `window.prompt` used to ask. */
  label: string;
  /** The primary button's own label. */
  submitLabel: string;
  /** The server's real bound (`admin/users.ts`'s `MAX_NOTE`), applied as the field's `maxlength`. */
  maxLength: number;
  /** Attempts the decision with the CURRENT text. Resolving `{ ok: true }` closes the drawer;
   *  `{ ok: false, message }` shows `message` in the drawer's own error slot and keeps the text. */
  submit: (note: string) => Promise<NoteDrawerOutcome>;
}

const SCRIM_STYLE = 'position: fixed; inset: 0; z-index: 900; background: rgba(0,58,112,.55); display: grid; place-items: center; padding: 24px;';
const BOX_STYLE = 'width: 100%; max-width: 520px; background: var(--color-white); border-radius: 12px; box-shadow: var(--shadow-xl); overflow: hidden; animation: rf-fade-up 300ms var(--easing-out) both;';
const HEADER_STYLE = 'display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 22px 26px; background: var(--rf-band);';
const TITLE_STYLE = 'font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;';
const SUBTITLE_STYLE = 'font-size: 13px; color: #494949; margin-top: 3px;';
const CLOSE_STYLE = 'flex: none; width: 30px; height: 30px; display: grid; place-items: center; background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer; color: var(--color-navy);';
const CLOSE_ICON_STYLE = 'flex: none; opacity: .75;';
const BODY_STYLE = 'padding: 24px 26px 26px;';
const LABEL_WRAP_STYLE = 'display: flex; flex-direction: column; gap: 6px;';
const LABEL_TEXT_STYLE = 'font-size: 12px; font-weight: 500; color: var(--color-steel);';
const TEXTAREA_STYLE = 'padding: 10px 13px; font-size: 14px; line-height: 1.5; color: var(--color-navy); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none; resize: vertical; width: 100%; box-sizing: border-box; font-family: inherit;';
const ERROR_STYLE = 'margin-top: 12px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; color: #494949;';
const BUTTON_ROW_STYLE = 'display: flex; gap: 10px; margin-top: 18px;';
const PRIMARY_STYLE = 'font-family: var(--rf-display); flex: 1; height: 48px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;';
const SECONDARY_STYLE = 'font-family: var(--rf-display); height: 48px; padding: 0 20px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;';

/**
 * Opens the drawer and resolves once it closes, however it closes — a successful `submit`, or the
 * reviewer's own cancel (the Cancel button, the close button, Escape, or a click on the scrim
 * outside the box — the same four the interest modal's own dismissal already answers to). Never
 * rejects: a refusal is the drawer's own business, shown in place.
 */
export function openNoteDrawer(config: NoteDrawerConfig): Promise<void> {
  return new Promise((resolve) => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const scrim = document.createElement('div');
    scrim.setAttribute('style', SCRIM_STYLE);

    const box = document.createElement('div');
    box.setAttribute('style', BOX_STYLE);
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', config.title);
    scrim.appendChild(box);

    const header = document.createElement('div');
    header.setAttribute('style', HEADER_STYLE);
    box.appendChild(header);

    const heading = document.createElement('div');
    const title = document.createElement('div');
    title.setAttribute('style', TITLE_STYLE);
    title.textContent = config.title;
    const subtitle = document.createElement('div');
    subtitle.setAttribute('style', SUBTITLE_STYLE);
    subtitle.textContent = config.subtitle;
    heading.appendChild(title);
    heading.appendChild(subtitle);
    header.appendChild(heading);

    const closeButton = document.createElement('button');
    closeButton.setAttribute('style', CLOSE_STYLE);
    // "Close", not "Cancel" (which the secondary button below already says verbatim): the two
    // controls do the same thing, but a shared accessible name would make them indistinguishable
    // to anything that queries by role and name — including the smoke suite's own real Chromium.
    closeButton.setAttribute('aria-label', 'Close');
    const closeIcon = document.createElement('img');
    closeIcon.src = '/assets/icons/delete-x.svg';
    closeIcon.alt = '';
    closeIcon.width = 12;
    closeIcon.height = 12;
    closeIcon.setAttribute('style', CLOSE_ICON_STYLE);
    closeButton.appendChild(closeIcon);
    header.appendChild(closeButton);

    const body = document.createElement('div');
    body.setAttribute('style', BODY_STYLE);
    box.appendChild(body);

    const labelWrap = document.createElement('label');
    labelWrap.setAttribute('style', LABEL_WRAP_STYLE);
    const labelText = document.createElement('span');
    labelText.setAttribute('style', LABEL_TEXT_STYLE);
    labelText.textContent = config.label;
    const textarea = document.createElement('textarea');
    textarea.setAttribute('style', TEXTAREA_STYLE);
    textarea.rows = 4;
    textarea.maxLength = config.maxLength;
    labelWrap.appendChild(labelText);
    labelWrap.appendChild(textarea);
    body.appendChild(labelWrap);

    const error = document.createElement('div');
    error.setAttribute('style', ERROR_STYLE);
    error.hidden = true;
    body.appendChild(error);

    const buttonRow = document.createElement('div');
    buttonRow.setAttribute('style', BUTTON_ROW_STYLE);
    const submitButton = document.createElement('button');
    submitButton.setAttribute('style', PRIMARY_STYLE);
    submitButton.textContent = config.submitLabel;
    submitButton.disabled = true;
    const cancelButton = document.createElement('button');
    cancelButton.setAttribute('style', SECONDARY_STYLE);
    cancelButton.textContent = 'Cancel';
    buttonRow.appendChild(submitButton);
    buttonRow.appendChild(cancelButton);
    body.appendChild(buttonRow);

    let busy = false;

    const close = (): void => {
      document.removeEventListener('keydown', onKeydown);
      scrim.remove();
      if (opener !== null) opener.focus();
      resolve();
    };

    const cancel = (): void => {
      if (busy) return;
      close();
    };

    const setBusy = (value: boolean): void => {
      busy = value;
      cancelButton.disabled = value;
      submitButton.disabled = value || textarea.value.trim() === '';
      textarea.disabled = value;
    };

    const attemptSubmit = (): void => {
      const note = textarea.value;
      if (busy || note.trim() === '') return;
      setBusy(true);
      config.submit(note).then((outcome) => {
        if (outcome.ok) { close(); return; }
        setBusy(false);
        error.textContent = outcome.message ?? 'That decision could not be recorded.';
        error.hidden = false;
        textarea.focus();
      });
    };

    textarea.addEventListener('input', () => {
      submitButton.disabled = textarea.value.trim() === '';
    });
    submitButton.addEventListener('click', attemptSubmit);
    cancelButton.addEventListener('click', cancel);
    closeButton.addEventListener('click', cancel);
    // The scrim's own click, never a bubble from the box — a click that starts and ends inside
    // the box (a drag-select of the textarea that releases over the scrim's padding) must not
    // read as an outside click, so this is target identity, not `contains`.
    scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) cancel(); });

    function onKeydown(e: KeyboardEvent): void {
      if (e.key === 'Escape') { e.preventDefault(); cancel(); }
    }
    document.addEventListener('keydown', onKeydown);

    document.body.appendChild(scrim);
    textarea.focus();
  });
}
