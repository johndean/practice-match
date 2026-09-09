"""Migration 062 (A-C16): closes B1 review's three findings.

1. The licence-gate trigger's UPDATE arm was untested -- every one of B1's four tests only ever
   inserted. `test_license_gate_refuses_an_update_onto_an_uncleared_dataset` below exercises an
   UPDATE that moves an existing row onto a blocked dataset; narrowing the trigger to
   `BEFORE INSERT` alone would make this fail even though every B1 test stayed green.

2. The DECLARE-free trigger read `dataset_registry.license_status` twice -- once in the `IF`,
   again inside the exception message's `COALESCE` -- so a concurrent status flip between the
   two reads could make the message name a status that is no longer current (the accept/refuse
   decision itself is unaffected: that is decided entirely by the first read).
   `test_license_gate_message_names_the_dataset_not_a_status` proves the message now names only
   the dataset key, which cannot go stale.

3. `geocode_review`, alone among this plan's listing-scoped tables, carried no foreign key to
   `listing`, so a deleted listing could leave orphan review rows behind.
   `test_geocode_review_cascades_when_its_listing_is_deleted` proves the same
   `ON DELETE CASCADE` its siblings (`practice_location`, `practice_catchment`, `market_metric`)
   use.
"""
import psycopg2
import pytest

from tests.census.listing_fixtures import make_listing


def test_license_gate_refuses_an_update_onto_an_uncleared_dataset(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'population', '2019\u20132023', 1, 'count', 'acs5', now())""", (lid,))
        with pytest.raises(psycopg2.errors.RaiseException) as e:
            cur.execute("""UPDATE market_metric SET source_dataset = 'pet_ownership'
                           WHERE listing_id=%s AND band='drive_10' AND metric_key='population' AND vintage='2019\u20132023'""", (lid,))
        assert "pet_ownership" in str(e.value)
        cur.execute("SELECT source_dataset FROM market_metric WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == "acs5"  # the refused UPDATE never took effect


def test_license_gate_message_names_the_dataset_not_a_status(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException) as e:
        cur.execute("""INSERT INTO market_metric (listing_id, band, metric_key, vintage, value_num, unit, source_dataset, computed_at)
                       VALUES (%s, 'drive_10', 'pet_households_licensed', 'n/a', 1, 'count', 'pet_ownership', now())""", (lid,))
    msg = str(e.value)
    assert "pet_ownership" in msg
    assert "blocked" not in msg  # the status word is gone; only the (stable) dataset key remains


def test_geocode_review_cascades_when_its_listing_is_deleted(conn):
    lid = make_listing(conn)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO geocode_review (listing_id, reason) VALUES (%s, 'fallback below rooftop')", (lid,))
        cur.execute("DELETE FROM listing WHERE id=%s", (lid,))
        cur.execute("SELECT count(*) FROM geocode_review WHERE listing_id=%s", (lid,))
        assert cur.fetchone()[0] == 0
