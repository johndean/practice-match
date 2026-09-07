"""The fourteen transactional templates (spec §5), text and HTML.

Three properties the spec asks for are structural here rather than a habit:

* **Escaped.** `render()` builds two substitution maps from the same params — the text one verbatim,
  the HTML one through `html.escape` (quotes included, so a param is safe inside an `href` too).
  A template body can therefore never interpolate an unescaped value into the HTML: the only map it
  is formatted with is the escaped one.
* **No tracking pixels.** There is no `<img>` anywhere in this module, and no remote asset of any
  kind — the HTML is one inline-styled card, so nothing about opening the mail is reported back.
* **No tokens in subjects.** Subjects carry no placeholders at all (`params` names only ever appear
  in bodies), which `tests/mail/test_templates.py` pins for every key.

`params` on each `Template` is the closed list of names that key's body uses. `render()` reads
nothing else out of the dict it is given, so a caller passing extra keys (the parametrized test
hands every template a `link`, a `note` and a `name`) cannot smuggle content into a template that
did not ask for it, and a caller passing too few gets an empty string rather than a `KeyError` in
the worker at send time.

`base_url` is the environment's own origin (`settings.link_base_url`) and appears in the footer of
every email, so a QA message is visibly a QA message. The `link` params are already absolute when
they reach here — `app.api.auth._link` builds them from the same setting — and are formatted
verbatim rather than re-joined onto `base_url`.
"""
from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PARA = "font-size:15px; line-height:1.7; color:#494949; margin:0 0 14px;"
QUIET = "font-size:13px; line-height:1.6; color:#767676; margin:18px 0 0;"
ANCHOR = "color:#1b5faa; text-decoration:underline;"
NOTE_BOX = "font-size:15px; line-height:1.7; color:#494949; margin:0 0 14px; padding:12px 14px; background:#f5f5f5; border-left:3px solid #d5d5d5;"


def _p(inner: str, style: str = PARA) -> str:
    """One paragraph. Built by concatenation, never an f-string: `inner` carries the `{placeholder}`
    markers `render()` substitutes later, and an f-string would need every one of them doubled."""
    return '<p style="' + style + '">' + inner + "</p>"


def design_paragraph(body: str) -> str:
    """One paragraph of copy PORTED FROM THE DESIGN, escaped.

    The design bodies are compile-time constants, so this is not an injection vector — but they are
    also the one kind of literal in this module that is expected to change without a developer
    rewriting it, and a re-word of the gate screen containing `&` or `<` would otherwise be ported
    into the HTML part verbatim and ship malformed markup, with the design oracle still green
    because it would find the raw string (fix round 1, F15)."""
    return _p(html.escape(body))


def _link_block(label: str) -> str:
    """The call to action, then the same URL in full — mail clients that strip anchors, and people
    who would rather see where a link goes before following it, both need the plain form."""
    return (
        _p('<a href="{link}" style="' + ANCHOR + '">' + label + "</a>")
        + _p("If that link does not open, paste this address into your browser:<br>{link}", QUIET)
    )


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class Template:
    subject: str
    text: str
    html: str
    params: tuple[str, ...] = ()


TEXT_DOC = "{body}\n\n--\nPractice Match · the VIN Foundation\n{base_url}\n"
HTML_DOC = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1"><title>{subject}</title></head>'
    '<body style="margin:0; padding:24px 12px; background:#f5f5f5;'
    " font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;\">"
    '<div style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid #e5e5e5; padding:26px 24px;">'
    '<p style="font-size:15px; font-weight:800; letter-spacing:-.005em; color:#1b5faa; margin:0 0 18px;">Practice Match</p>'
    "{body}"
    '<p style="' + QUIET + '">Practice Match · the VIN Foundation<br>'
    '<a href="{base_url}" style="' + ANCHOR + '">{base_url}</a></p>'
    "</div></body></html>"
)

# The two bodies below are PORTED VERBATIM from the approved design's gate screen
# (`docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html`,
# `statusMap.pending` line 2344 and `statusMap.rejected` line 2351) — spec §5: "Copy follows the
# design's pending/declined screens", CLAUDE.md: "reference open first, port verbatim". The brief
# paraphrased both ("The VIN Foundation reviews each request…", "…ask for a second look"); John's
# ruling of 2026-09-07 is that the design governs. `tests/mail/test_templates.py` reads the
# strings out of the design file rather than repeating them, so neither can drift alone.
_HAND_REVIEW = (
    "VIN Foundation staff review each request by hand, usually within two business days. "
    "You will get an email the moment a decision is made. Nothing else is needed from you right now."
)
_DECLINED = (
    "Your request could not be approved as submitted. The most common reason is an affiliation the "
    "VIN Foundation could not confirm. You may reply with additional information and ask for a second review."
)
_NOT_YOU_PASSWORD = "If this was not you, reset your password and tell the VIN Foundation."

TEMPLATES: dict[str, Template] = {
    "verify_email": Template(
        subject="Confirm your email address for Practice Match",
        text="Confirm this address to finish creating your Practice Match account:\n\n{link}\n\n"
             "The link works for 24 hours and can be used once. If you did not ask for an account, ignore this email.",
        html=_p("Confirm this address to finish creating your Practice Match account.")
             + _link_block("Confirm my email address")
             + _p("The link works for 24 hours and can be used once. If you did not ask for an account, ignore this email.", QUIET),
        params=("link",),
    ),
    # I4 fix round 1, Critical 1: a sign-up for an address that ALREADY has an account does the same
    # work and returns the same answer, so the only place the difference can surface is here — in the
    # mailbox of the person who owns the address, who is also the one entitled to know.
    "account_exists": Template(
        subject="Someone tried to create a Practice Match account with this address",
        text="Somebody signed up for Practice Match with this email address, which already has an account.\n\n"
             "No new account was created and nothing has changed. If it was you, sign in as usual — or reset your "
             "password if you have forgotten it. If it was not you, no action is needed.",
        html=_p("Somebody signed up for Practice Match with this email address, which already has an account.")
             + _p("No new account was created and nothing has changed. If it was you, sign in as usual — or reset your "
                  "password if you have forgotten it. If it was not you, no action is needed."),
    ),
    "application_received": Template(
        subject="Your Practice Match application was received",
        text=_HAND_REVIEW,
        html=design_paragraph(_HAND_REVIEW),
    ),
    "application_approved": Template(
        subject="Your Practice Match application was approved",
        text="Your application was approved. You can sign in and start browsing listings.\n\n"
             "Sellers decide what to disclose and when; expressing interest is the first step.",
        html=_p("Your application was approved. You can sign in and start browsing listings.")
             + _p("Sellers decide what to disclose and when; expressing interest is the first step."),
    ),
    "application_declined": Template(
        subject="A decision on your Practice Match application",
        text=_DECLINED + "\n\nWhat the reviewer wrote:\n\n{note}",
        html=design_paragraph(_DECLINED) + _p("What the reviewer wrote:") + _p("{note}", NOTE_BOX),
        params=("note",),
    ),
    "application_info_requested": Template(
        subject="More information is needed for your Practice Match application",
        text="Your application is on hold until the VIN Foundation has one more thing from you. "
             "Sign in and reply from the application screen.\n\nWhat the reviewer asked for:\n\n{note}",
        html=_p("Your application is on hold until the VIN Foundation has one more thing from you. "
                "Sign in and reply from the application screen.")
             + _p("What the reviewer asked for:") + _p("{note}", NOTE_BOX),
        params=("note",),
    ),
    "seller_application_received": Template(
        subject="Your Practice Match seller application was received",
        text=_HAND_REVIEW,
        html=design_paragraph(_HAND_REVIEW),
    ),
    "seller_application_approved": Template(
        subject="Your Practice Match seller application was approved",
        text="You can now list a practice on Practice Match. A staff reviewer checks each listing before it "
             "goes live — usually within two business days — and you can keep editing while it waits.",
        html=_p("You can now list a practice on Practice Match. A staff reviewer checks each listing before it "
                "goes live — usually within two business days — and you can keep editing while it waits."),
    ),
    "seller_application_declined": Template(
        subject="A decision on your Practice Match seller application",
        text=_DECLINED + "\n\nWhat the reviewer wrote:\n\n{note}",
        html=design_paragraph(_DECLINED) + _p("What the reviewer wrote:") + _p("{note}", NOTE_BOX),
        params=("note",),
    ),
    "password_reset": Template(
        subject="Reset your Practice Match password",
        text="Use this link to choose a new Practice Match password:\n\n{link}\n\n"
             "The link works for one hour and can be used once. Asking for another one cancels this "
             "link. If you did not ask for it, nothing has changed and you can ignore this email.",
        html=_p("Use this link to choose a new Practice Match password.")
             + _link_block("Choose a new password")
             + _p("The link works for one hour and can be used once. Asking for another one cancels this "
                  "link. If you did not ask for it, nothing has changed and you can ignore this email.", QUIET),
        params=("link",),
    ),
    "password_changed": Template(
        subject="Your Practice Match password was changed",
        text="Your Practice Match password has just been changed, and every other signed-in session was "
             "ended.\n\n" + _NOT_YOU_PASSWORD,
        html=_p("Your Practice Match password has just been changed, and every other signed-in session was ended.")
             + _p(_NOT_YOU_PASSWORD, QUIET),
    ),
    # Spec §3's compensating control for a staff/admin account with no second factor: a sign-in from
    # an (ip, user agent) pair that account has not used before is reported to its owner.
    "signin_new_device": Template(
        subject="New sign-in to your Practice Match account",
        text="Your Practice Match account was signed in to from a device or network it has not been used "
             "from before.\n\nWhen: {when}\nIP address: {ip}\nBrowser: {user_agent}\n\n" + _NOT_YOU_PASSWORD,
        html=_p("Your Practice Match account was signed in to from a device or network it has not been used from before.")
             + _p("When: {when}<br>IP address: {ip}<br>Browser: {user_agent}", NOTE_BOX)
             + _p(_NOT_YOU_PASSWORD, QUIET),
        params=("when", "ip", "user_agent"),
    ),
    "account_suspended": Template(
        subject="Your Practice Match account has been suspended",
        text="Your Practice Match account has been suspended and cannot be used until it is restored. "
             "A suspension is reversible — reply with anything that helps and it will be looked at again."
             "\n\nWhy:\n\n{note}",
        html=_p("Your Practice Match account has been suspended and cannot be used until it is restored. "
                "A suspension is reversible — reply with anything that helps and it will be looked at again.")
             + _p("Why:") + _p("{note}", NOTE_BOX),
        params=("note",),
    ),
    "account_revoked": Template(
        subject="Your Practice Match access has been withdrawn",
        text="Your access to Practice Match has been withdrawn and every signed-in session has ended."
             "\n\nWhy:\n\n{note}",
        html=_p("Your access to Practice Match has been withdrawn and every signed-in session has ended.")
             + _p("Why:") + _p("{note}", NOTE_BOX),
        params=("note",),
    ),
}


def render(key: str, params: Mapping[str, Any], *, base_url: str) -> Rendered:
    """The subject, plain-text body and HTML body for `key`.

    A declared param that is missing — or explicitly `None`, which is what an optional staff note
    arrives as — renders as an empty string: a worker draining the outbox must never fail on a row
    it can still deliver, and "None" in the middle of a sentence is worse than nothing."""
    template = TEMPLATES[key]
    plain = {name: "" if params.get(name) is None else str(params[name]) for name in template.params}
    escaped = {name: html.escape(value) for name, value in plain.items()}
    return Rendered(
        subject=template.subject,
        text=TEXT_DOC.format(body=template.text.format(**plain), base_url=base_url),
        html=HTML_DOC.format(subject=html.escape(template.subject), body=template.html.format(**escaped), base_url=html.escape(base_url)),
    )
