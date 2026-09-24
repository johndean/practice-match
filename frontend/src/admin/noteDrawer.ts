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
  /** Who the decision is about, under the title, the interest modal's own `modal.sub` idiom.
   *  OPTIONAL (Task 7): a caller with nobody to name draws no element rather than an empty one,
   *  which is the `sc-if` discipline every conditional line in the design already follows. */
  subtitle?: string;
  /** The field's own label — the exact question `window.prompt` used to ask. */
  label: string;
  /** The primary button's own label. */
  submitLabel: string;
  /** The server's real bound (`admin/users.ts`'s `MAX_NOTE`), applied as the field's `maxlength`. */
  maxLength: number;
  /** Whether a BLANK field may be submitted (Task 7, findings U1/U2). A decision's note is
   *  mandatory, so the default is false and the primary button stays disabled until something is
   *  typed. The step-6 tile's describe surface sets it: `caption_asset` treats blank and null as
   *  one intent — "the seller is taking the description back" — so a blank there is an answer,
   *  not a missing one. */
  allowEmpty?: boolean;
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
// The interest modal's own SENT branch (`modal.isSent`), which is already exactly a
// confirmation's shape: one sentence in a padded body above a primary-and-secondary button row.
const CONFIRM_BODY_STYLE = 'padding: 26px;';
const CONFIRM_TEXT_STYLE = 'font-size: 15px; line-height: 1.7; color: #494949; margin: 0;';
const CONFIRM_BUTTON_ROW_STYLE = 'display: flex; gap: 10px; margin-top: 20px;';
const LABEL_WRAP_STYLE = 'display: flex; flex-direction: column; gap: 6px;';
const LABEL_TEXT_STYLE = 'font-size: 12px; font-weight: 500; color: var(--color-steel);';
const TEXTAREA_STYLE = 'padding: 10px 13px; font-size: 14px; line-height: 1.5; color: var(--color-navy); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none; resize: vertical; width: 100%; box-sizing: border-box; font-family: inherit;';
const ERROR_STYLE = 'margin-top: 12px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; color: #494949;';
// The WIZARD STEP 7 toggle row, declaration for declaration (`Practice Match V3.dc.html`'s own
// `wiz.toggles` block): the design's established shape for a set of disclosure choices, which is
// exactly what this drawer asks for one surface over. The intro paragraph is the wizard step's own
// `blurb` style.
const CHOICE_INTRO_STYLE = 'font-size: 14px; line-height: 1.55; color: #494949; margin: 0 0 16px; max-width: 60ch;';
const CHOICE_LIST_STYLE = 'display: flex; flex-direction: column; gap: 10px;';
const CHOICE_ROW_STYLE = 'display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; background: var(--color-off-white); border: 1px solid var(--rf-line); border-radius: 8px; cursor: pointer;';
const CHOICE_BOX_STYLE = 'margin-top: 3px; width: 16px; height: 16px; accent-color: var(--color-blue);';
const CHOICE_LABEL_STYLE = 'display: block; font-size: 14px; font-weight: 500; color: var(--color-navy);';
const BUTTON_ROW_STYLE = 'display: flex; gap: 10px; margin-top: 18px;';
const PRIMARY_STYLE = 'font-family: var(--rf-display); flex: 1; height: 48px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;';
const SECONDARY_STYLE = 'font-family: var(--rf-display); height: 48px; padding: 0 20px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;';


/**
 * The drawer's outer shell — scrim, box, header (title, optional subtitle, 30 px close button) and
 * a padded body — shared by BOTH surfaces in this module rather than written twice (Task 7 fix
 * round, John's ruling of 2026-09-24). Every declaration is the INTEREST MODAL's own, copied
 * verbatim the way `admin/users.ts`'s `cell()`/`A()` copy `adminVals()`'s: this is app-only glue
 * the reference never renders, so it carries no amendment.
 *
 * The `subtitle` is drawn only when the caller has one to name — an empty element is the thing
 * the design's own `sc-if` discipline exists to avoid, and the test is TRUTHINESS rather than
 * `!== undefined` (fix round 2, Important-2) because `""` is a caller with nothing to name just as
 * surely as an omitted one, and the design's own idiom is truthy: `sc-if value="{{ u.pill }}"`
 * ports to `v-if="u?.pill"`. The sentence above was false for `""` until this said so.
 */
function shell(config: { title: string; subtitle?: string }, bodyStyle: string): {
  scrim: HTMLElement; box: HTMLElement; closeButton: HTMLButtonElement; body: HTMLElement;
} {
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
  heading.appendChild(title);
  if (config.subtitle) {
    const subtitle = document.createElement('div');
    subtitle.setAttribute('style', SUBTITLE_STYLE);
    subtitle.textContent = config.subtitle;
    heading.appendChild(subtitle);
  }
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
  body.setAttribute('style', bodyStyle);
  box.appendChild(body);
  return { scrim, box, closeButton, body };
}

/**
 * Opens the drawer and resolves once it closes, however it closes — a successful `submit`, or the
 * reviewer's own cancel (the Cancel button, the close button, Escape, or a click on the scrim
 * outside the box — the same four the interest modal's own dismissal already answers to). Never
 * rejects: a refusal is the drawer's own business, shown in place.
 */
export function openNoteDrawer(config: NoteDrawerConfig): Promise<void> {
  return new Promise((resolve) => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const blankIsAnAnswer = config.allowEmpty === true;

    const { scrim, box, closeButton, body } = shell(config, BODY_STYLE);

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
    submitButton.disabled = !blankIsAnAnswer;
    const cancelButton = document.createElement('button');
    cancelButton.setAttribute('style', SECONDARY_STYLE);
    cancelButton.textContent = 'Cancel';
    buttonRow.appendChild(submitButton);
    buttonRow.appendChild(cancelButton);
    body.appendChild(buttonRow);

    const unanswered = (): boolean => !blankIsAnAnswer && textarea.value.trim() === '';
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
      submitButton.disabled = value || unanswered();
      textarea.disabled = value;
    };

    const attemptSubmit = (): void => {
      const note = textarea.value;
      if (busy || unanswered()) return;
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
      submitButton.disabled = unanswered();
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


export interface ConfirmDrawerConfig {
  /** The action's own words, naming WHAT is being destroyed ("Remove this photograph"), never a
   *  generic "Are you sure?" — John's ruling of 2026-09-24. */
  title: string;
  /** The thing itself, under the title: the photograph's own description or the document's own
   *  filename, in the interest modal's own `modal.sub` idiom. */
  subtitle?: string;
  /** One sentence saying what happens and that it cannot be taken back. */
  body: string;
  /** The destructive button's own label — the same word as the control that opened it. */
  confirmLabel: string;
}

/**
 * The confirm-shaped variant of the drawer above (Task 7 fix round; John's ruling of 2026-09-24:
 * "Remove must ask before it destroys" — a seller who misclicks loses an uploaded photograph
 * permanently, and photographs are the field the design itself says do more than any other to
 * bring the right buyer to a listing).
 *
 * The SAFE action is the SECONDARY button, which is the ruling and also the interest modal's own
 * arrangement: the destructive act is the `flex: 1` primary the seller came here to perform, and
 * Cancel is the bordered secondary beside it. Every dismissal the note drawer answers to — Cancel,
 * the close button, Escape, a click on the scrim outside the box — resolves FALSE, so nothing but
 * a deliberate press of the primary destroys anything.
 *
 * AND THE SAFE ACTION IS THE ONE THAT TAKES FOCUS (fix round 2, Important-1), which the ruling
 * reaches as surely as the layout does: a keyboard seller presses Enter on a tile's Remove button
 * and keydown -> click -> this drawer opens inside ONE keystroke, so a focused PRIMARY would be
 * sitting under the OS's own auto-repeat (~500 ms) and the photograph would be destroyed without
 * the dialog having been read. `openNoteDrawer` focuses its field because a field is where that
 * reviewer's work begins; here there is nothing to type and the thing to protect is the default.
 *
 * It asks nothing, so it carries no field, no error slot and no busy state: the caller does the
 * work AFTER this resolves, and a refusal lands where that caller's own errors land (for the
 * step-6 tile, the wizard's own `wizErr` slot).
 */
export function openConfirmDrawer(config: ConfirmDrawerConfig): Promise<boolean> {
  return new Promise((resolve) => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const { scrim, closeButton, body } = shell(config, CONFIRM_BODY_STYLE);

    const text = document.createElement('p');
    text.setAttribute('style', CONFIRM_TEXT_STYLE);
    text.textContent = config.body;
    body.appendChild(text);

    const buttonRow = document.createElement('div');
    buttonRow.setAttribute('style', CONFIRM_BUTTON_ROW_STYLE);
    const confirmButton = document.createElement('button');
    confirmButton.setAttribute('style', PRIMARY_STYLE);
    confirmButton.textContent = config.confirmLabel;
    const cancelButton = document.createElement('button');
    cancelButton.setAttribute('style', SECONDARY_STYLE);
    cancelButton.textContent = 'Cancel';
    buttonRow.appendChild(confirmButton);
    buttonRow.appendChild(cancelButton);
    body.appendChild(buttonRow);

    const close = (answer: boolean): void => {
      document.removeEventListener('keydown', onKeydown);
      scrim.remove();
      if (opener !== null) opener.focus();
      resolve(answer);
    };

    confirmButton.addEventListener('click', () => close(true));
    cancelButton.addEventListener('click', () => close(false));
    closeButton.addEventListener('click', () => close(false));
    // The scrim's own click, never a bubble from the box — `openNoteDrawer`'s own reason.
    scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(false); });

    function onKeydown(e: KeyboardEvent): void {
      if (e.key === 'Escape') { e.preventDefault(); close(false); }
    }
    document.addEventListener('keydown', onKeydown);

    document.body.appendChild(scrim);
    cancelButton.focus();
  });
}


export interface ChoiceDrawerOption {
  /** The value handed back — a capability name (`app.disclosure.levels.CAPABILITIES`). */
  value: string;
  /** What the seller reads — `LEVEL_LABEL`'s own word for it (`frontend/src/admin/requests.ts`),
   *  never a second spelling written here. */
  label: string;
}

export interface ChoiceDrawerConfig {
  /** The drawer's own title — the action's own label, so it reads the same word as the button that
   *  opened it (`openNoteDrawer`'s own rule). */
  title: string;
  /** Who the decision is about, under the title — the buyer's own name. */
  subtitle?: string;
  /** One sentence above the list saying what the choice is. */
  intro: string;
  options: ChoiceDrawerOption[];
  /** Ticked when the drawer opens — on the CHANGE path, exactly what this buyer already holds, so
   *  a seller narrowing a grant starts from the truth rather than from blank. */
  selected: string[];
  /** The primary button's own label. */
  submitLabel: string;
}

/**
 * The third variant of this module's shell (D-C67, John, 2026-09-24: "all toggles must be fully
 * functional and SELLER must be able to manage it all and per seller"): a set of choices, answered
 * with the ones ticked.
 *
 * COMPOSED FROM V3'S OWN ELEMENTS and inventing no control, colour or copy. The shell — scrim, box,
 * title, subtitle, 30 px close button, padded body and the primary/secondary pair — is the one
 * `openNoteDrawer` and `openConfirmDrawer` already share, which is the INTEREST MODAL's own. The
 * rows are the WIZARD STEP 7 toggle rows, whose own blurb ("You decide what an approved buyer sees
 * before you have spoken to them.") is the sentence this drawer's callers pass as `intro`: step 7
 * is where this product already asks a seller this question, one buyer wider.
 *
 * WHAT IT ANSWERS: the ticked values, or `null` for every dismissal — Cancel, the close button,
 * Escape, and a click on the scrim outside the box, the same four every drawer here answers to.
 * `null` is "the seller did not decide" and is NOT `[]`, which is "the seller decided to release
 * nothing"; the two are different answers and `app.disclosure.requests._chosen_capabilities` reads
 * them as different answers, so this surface must not flatten them either.
 *
 * THE PRIMARY IS DISABLED WHILE NOTHING IS TICKED — `openNoteDrawer`'s own `allowEmpty: false`
 * default, for the same reason: a "Share more" that shares nothing is a decline, and Decline is
 * the button beside it. The server nevertheless accepts and stores an empty set, fail-closed,
 * because a client is not the place that guarantee lives (`tests/api/test_seller_requests.py`'s
 * own `test_approve_with_an_empty_array_releases_nothing_over_the_wire`).
 */
export function openChoiceDrawer(config: ChoiceDrawerConfig): Promise<string[] | null> {
  return new Promise((resolve) => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const { scrim, closeButton, body } = shell(config, BODY_STYLE);
    const chosen = new Set(config.selected);

    const intro = document.createElement('p');
    intro.setAttribute('style', CHOICE_INTRO_STYLE);
    intro.textContent = config.intro;
    body.appendChild(intro);

    const list = document.createElement('div');
    list.setAttribute('style', CHOICE_LIST_STYLE);
    body.appendChild(list);

    const buttonRow = document.createElement('div');
    buttonRow.setAttribute('style', BUTTON_ROW_STYLE);
    const submitButton = document.createElement('button');
    submitButton.setAttribute('style', PRIMARY_STYLE);
    submitButton.textContent = config.submitLabel;
    const cancelButton = document.createElement('button');
    cancelButton.setAttribute('style', SECONDARY_STYLE);
    cancelButton.textContent = 'Cancel';
    buttonRow.appendChild(submitButton);
    buttonRow.appendChild(cancelButton);
    body.appendChild(buttonRow);

    const settle = (): void => {
      submitButton.disabled = chosen.size === 0;
    };

    for (const option of config.options) {
      const row = document.createElement('label');
      row.setAttribute('style', CHOICE_ROW_STYLE);
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.setAttribute('style', CHOICE_BOX_STYLE);
      box.value = option.value;
      box.checked = chosen.has(option.value);
      const text = document.createElement('span');
      text.setAttribute('style', CHOICE_LABEL_STYLE);
      text.textContent = option.label;
      box.addEventListener('change', () => {
        if (box.checked) chosen.add(option.value);
        else chosen.delete(option.value);
        settle();
      });
      row.appendChild(box);
      row.appendChild(text);
      list.appendChild(row);
    }
    settle();

    const close = (answer: string[] | null): void => {
      document.removeEventListener('keydown', onKeydown);
      scrim.remove();
      if (opener !== null) opener.focus();
      resolve(answer);
    };

    // The ORDER the options were declared in, never the order the seller happened to tick them:
    // the caller hands these to an API and reads them back in a sentence, and a set has no order
    // of its own to preserve.
    const ticked = (): string[] => config.options.filter((o) => chosen.has(o.value)).map((o) => o.value);

    submitButton.addEventListener('click', () => { if (chosen.size > 0) close(ticked()); });
    cancelButton.addEventListener('click', () => close(null));
    closeButton.addEventListener('click', () => close(null));
    // The scrim's own click, never a bubble from the box — `openNoteDrawer`'s own reason.
    scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(null); });

    function onKeydown(e: KeyboardEvent): void {
      if (e.key === 'Escape') { e.preventDefault(); close(null); }
    }
    document.addEventListener('keydown', onKeydown);

    document.body.appendChild(scrim);
    // The first choice takes focus, `openNoteDrawer`'s own reason: the seller's work begins at the
    // list. Nothing here is destructive, so `openConfirmDrawer`'s safe-action rule does not apply.
    const first = list.querySelector('input');
    if (first instanceof HTMLInputElement) first.focus();
  });
}
