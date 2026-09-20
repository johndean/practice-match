from app.auth.labels import initials, role_label


def test_role_label_matches_the_design_persona_string():
    assert role_label(frozenset({"buyer"}), "StartUp Club") == "Approved buyer · StartUp Club"
    assert role_label(frozenset({"seller"}), None) == "Approved seller"
    assert role_label(frozenset({"staff", "buyer"}), None) == "VIN Foundation staff"
    assert role_label(frozenset({"admin", "staff"}), "x") == "VIN Foundation admin · x"
    assert role_label(frozenset(), None) == "Applicant"


def test_the_buyer_and_seller_branch_is_removed_under_ruling_d_c59():
    """Ruling D-C59 (John, 2026-09-20): a buyer is never a seller, enforced in the database
    (`migrations/100_role_exclusivity.sql`) so no NEW account can ever hold both roles active at
    once. The `{"buyer", "seller"} <= roles` branch that used to read "Approved buyer and seller"
    is gone — `role_label` is a pure function of whatever `frozenset` it is handed, so calling it
    with both roles is still POSSIBLE (an account that already held both before this migration
    shipped is left untouched, by the ruling's own "Open" section), and it now falls through to the
    next branch in the `elif` chain exactly as a `seller`-only account does."""
    assert role_label(frozenset({"buyer", "seller"}), None) == "Approved seller"
    assert role_label(frozenset({"buyer", "seller"}), "StartUp Club") == "Approved seller · StartUp Club"


def test_initials():
    assert initials("Dr. Rachel Mendes") == "RM" and initials("Jane Doe, DVM") == "JD" and initials("") == "?"
