import re
from pathlib import Path

import pytest

from app.mail import templates as TP

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design-reference" / "design_handoff_practice_match_v2" / "Practice Match V2.dc.html"


def design_status_body(key: str) -> str:
    """The `body:` string of one `statusMap` entry in the APPROVED DESIGN, read out of the design
    file itself (`logic.js`'s `gate` screen, `pending` and `rejected`).

    Read rather than copied because CLAUDE.md's first rule is "reference open first, port
    verbatim", and spec §5 says the mail copy "follows the design's pending/declined screens".
    A copy pasted into an assertion drifts the moment the screen is re-worded; this cannot."""
    match = re.search(rf'\n\s+{key}: \{{.*?\n\s+body: "(.*?)",\n', DESIGN.read_text(), re.DOTALL)
    assert match, f"the design's statusMap has no {key} body — has the reference moved?"
    return match.group(1)


@pytest.mark.parametrize("key", sorted(TP.TEMPLATES))
def test_every_template_renders_text_and_html_with_the_environment_host(key):
    r = TP.render(key, {"link": "https://qa.foundation.vin/verify?token=abc", "note": "Which practice?", "name": "<script>x</script>"}, base_url="https://qa.foundation.vin")
    assert r.subject and r.text and r.html and "qa.foundation.vin" in (r.text + r.html) if "link" in TP.TEMPLATES[key].params else True
    assert "<script>" not in r.html and "&lt;script&gt;" in r.html if "name" in TP.TEMPLATES[key].params else True
    assert "token=" not in r.subject


def test_application_received_uses_the_design_copy():
    r = TP.render("application_received", {}, base_url="https://foundation.vin")
    assert "usually within two business days" in r.text and r.subject == "Your Practice Match application was received"
    # ...and VERBATIM, not merely in the same spirit: the design's own "under review" body
    # (`Practice Match V2.dc.html`, statusMap.pending). Both the buyer and the seller
    # acknowledgement echo the same screen.
    body = design_status_body("pending")
    for key in ("application_received", "seller_application_received"):
        rendered = TP.render(key, {}, base_url="https://foundation.vin")
        assert body in rendered.text, key
        assert body in rendered.html, key


# --- supplemental (not in the brief's Step 1 — the spec's escaping/no-pixel rules, and branches) ---


def test_the_fourteen_keys_are_exactly_the_ones_the_outbox_accepts():
    """`app.mail.outbox.TEMPLATES` is the gate on the REQUEST path (a typo there is refused at
    enqueue time) and this module is what the WORKER renders. Two lists, one truth: a key added to
    one and not the other is either a row that can never be rendered or a template nothing can
    reach, and both would sit undetected until a real person failed to get an email."""
    from app.mail.outbox import TEMPLATES as ACCEPTED

    assert set(TP.TEMPLATES) == set(ACCEPTED)
    assert len(TP.TEMPLATES) == 14


def test_application_declined_uses_the_designs_declined_screen():
    """Verbatim from the design's `rejected` gate screen — the buyer and the seller decline share it."""
    body = design_status_body("rejected")
    assert "ask for a second review" in body                       # the design's words, not "a second look"
    for key in ("application_declined", "seller_application_declined"):
        r = TP.render(key, {"note": "Affiliation not verified"}, base_url="https://foundation.vin")
        assert body in r.text, key
        assert body in r.html, key
        assert "Affiliation not verified" in r.text and "Affiliation not verified" in r.html, key


def test_free_text_from_a_reviewer_or_a_browser_is_escaped_in_the_html():
    """Spec §5's "escaped": `note` is typed by a staff reviewer and `user_agent` is supplied by
    whoever signed in, so both reach a mailbox as markup if nothing escapes them. S5."""
    declined = TP.render("application_declined", {"note": '<img src=x onerror="alert(1)">'}, base_url="https://qa.foundation.vin")
    assert "<img" not in declined.html and "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in declined.html
    assert '<img src=x onerror="alert(1)">' in declined.text  # the plain part is not markup and is left alone

    device = TP.render("signin_new_device", {"when": "2026-09-07T10:00:00+00:00", "ip": "203.0.113.5",
                                             "user_agent": "<script>x</script>"}, base_url="https://qa.foundation.vin")
    assert "<script>" not in device.html and "&lt;script&gt;" in device.html


def test_a_missing_or_null_param_renders_as_nothing_rather_than_none():
    """`app.api.admin_users` enqueues `{"note": note}` for every decision, and `note` is optional on
    an approval — "None" in the middle of a sentence would be the visible result."""
    for params in ({}, {"note": None}):
        r = TP.render("account_suspended", params, base_url="https://qa.foundation.vin")
        assert "None" not in r.text and "None" not in r.html


def test_no_template_carries_a_tracking_pixel_or_any_remote_asset():
    """Spec §5: "no tracking pixels". The only URL any of these mails may contain is the one the
    recipient is meant to follow — the link param and the environment's own footer."""
    for key, template in TP.TEMPLATES.items():
        assert "<img" not in template.html.lower(), key
        assert "http" not in template.html.replace("{link}", ""), key
    assert "<img" not in TP.HTML_DOC.lower()


def test_the_footer_names_the_environment_the_mail_came_from():
    """A QA message must be visibly a QA message: `base_url` is the environment's own origin."""
    r = TP.render("password_changed", {}, base_url="https://qa.foundation.vin")
    assert "https://qa.foundation.vin" in r.text and 'href="https://qa.foundation.vin"' in r.html
