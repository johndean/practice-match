from app.auth.labels import initials, role_label


def test_role_label_matches_the_design_persona_string():
    assert role_label(frozenset({"buyer"}), "StartUp Club") == "Approved buyer · StartUp Club"
    assert role_label(frozenset({"buyer", "seller"}), None) == "Approved buyer and seller"
    assert role_label(frozenset({"seller"}), None) == "Approved seller"
    assert role_label(frozenset({"staff", "buyer"}), None) == "VIN Foundation staff"
    assert role_label(frozenset({"admin", "staff"}), "x") == "VIN Foundation admin · x"
    assert role_label(frozenset(), None) == "Applicant"


def test_initials():
    assert initials("Dr. Rachel Mendes") == "RM" and initials("Jane Doe, DVM") == "JD" and initials("") == "?"
