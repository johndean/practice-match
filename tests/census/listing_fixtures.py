import uuid


def make_listing(conn, *, id=None, city="Cedar Park", state="TX", zip="78613", street="1 Main St", status="published", sqft=3000, est=2005, price=1200000):
    """Minimal listing row. The column list must match Sub-project 2's listing schema —
    update THIS function only if SP2 names them differently.

    Adapted from the brief's illustrative INSERT (id, street, city, state, zip, status only):
    `listing` (016_listing.sql) also requires `slug`, `name`, `area`, `type`, `market` and
    `source` NOT NULL with no default, and `type`/`source` are CHECK-constrained (one of the
    design's five practice types; 'seed' or 'seller'). `slug` is derived from the row's own id
    so repeated calls never collide; `area` and `market` are derived from the caller's
    `city`/`state` so a listing_id-keyed test reads as the same place throughout. Migrations 030
    and 034 (the seller lifecycle) additionally require `est` and `price` for any submittable row
    and `sqft` for a published one, which is why the fixture carries them with realistic defaults
    consistent with the seeded demo hospitals. Every other column (`photos`, `photo_captions`,
    `status`'s default, timestamps, disclosure flags) keeps SP2's own default.
    """
    lid = str(id or uuid.uuid4())
    slug = f"census-fixture-{lid[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (id, slug, name, street, city, state, zip, status, area, type, market, source, sqft, est, price)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (lid, slug, "Census Fixture Hospital", street, city, state, zip, status, city, "Small animal", f"{city}, {state}", "seed", sqft, est, price),
        )
    return lid
