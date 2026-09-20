"""Human-facing role labels and name initials (design persona strings, spec §4).

The `{"buyer", "seller"} <= roles` branch that used to read "Approved buyer and seller" is REMOVED
under ruling D-C59 (John, 2026-09-20, verbatim: "a buyer can not be a seller and a seller can not
be a buyer"; spec docs/superpowers/specs/2026-09-20-account-role-exclusivity-ruling.md). Measured
before removal, this bundle's own dead-code rule (A28.2-A28.9's precedent): its only caller is
`app/api/auth.py::me_payload`, which reads `frozenset(roles)` off `role_grant` — a table
`migrations/100_role_exclusivity.sql` now refuses to hold both roles active on one account, so no
NEW account can ever reach this branch again. An account that already held both roles before that
migration shipped (unknown; the ruling's own "Open" section does not say) is left exactly as it
was — nothing here migrates a role — and would, from this commit, compute "Approved seller" instead
(the next branch below, since `elif "seller" in roles` still matches): a labelling consequence of
removing an unreachable-going-forward branch, not a role change, and recorded rather than hidden."""
from __future__ import annotations


def role_label(roles: frozenset[str], affiliation: str | None) -> str:
    if "admin" in roles:
        base = "VIN Foundation admin"
    elif "staff" in roles:
        base = "VIN Foundation staff"
    elif "seller" in roles:
        base = "Approved seller"
    elif "buyer" in roles:
        base = "Approved buyer"
    else:
        base = "Applicant"
    return f"{base} · {affiliation}" if affiliation else base


def initials(name: str) -> str:
    parts = [p for p in name.replace(",", " ").split() if p and p[0].isalpha() and p.rstrip(".").lower() not in {"dr", "dvm", "vmd", "mr", "ms", "mrs"}]
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else (parts[0][0].upper() if parts else "?")
