import pytest

from app.mail import templates as TP


@pytest.mark.parametrize("key", sorted(TP.TEMPLATES))
def test_every_template_renders_text_and_html_with_the_environment_host(key):
    r = TP.render(key, {"link": "https://qa.foundation.vin/verify?token=abc", "note": "Which practice?", "name": "<script>x</script>"}, base_url="https://qa.foundation.vin")
    assert r.subject and r.text and r.html and "qa.foundation.vin" in (r.text + r.html) if "link" in TP.TEMPLATES[key].params else True
    assert "<script>" not in r.html and "&lt;script&gt;" in r.html if "name" in TP.TEMPLATES[key].params else True
    assert "token=" not in r.subject


def test_application_received_uses_the_design_copy():
    r = TP.render("application_received", {}, base_url="https://foundation.vin")
    assert "usually within two business days" in r.text and r.subject == "Your Practice Match application was received"


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
    r = TP.render("application_declined", {"note": "Affiliation not verified"}, base_url="https://foundation.vin")
    assert "could not be approved as submitted" in r.text
    assert "an affiliation the VIN Foundation could not confirm" in r.text
    assert "Affiliation not verified" in r.text and "Affiliation not verified" in r.html


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
