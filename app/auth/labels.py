"""Human-facing role labels and name initials (design persona strings, spec §4)."""
from __future__ import annotations


def role_label(roles: frozenset[str], affiliation: str | None) -> str:
    if "admin" in roles:
        base = "VIN Foundation admin"
    elif "staff" in roles:
        base = "VIN Foundation staff"
    elif {"buyer", "seller"} <= roles:
        base = "Approved buyer and seller"
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
