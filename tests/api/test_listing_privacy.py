"""The publishing gate at the three publication routes, and the listing setting's one writer.

Spec 2026-09-09 C.8 and C.1; directives 11, 7 and 16. Started by Task P10 and extended by P12 and
P13 — scenario M's rows live here.

**Why the pipeline is not run.** The gate reads STATES, never redaction output, so every row below
is walked through `app/privacy/record.py`'s OWN writers — the same transitions
`app/tasks/media.py` will make once Task P8 lands — rather than through a task that does not exist
on this branch. `_pipelined` is that walk, and it is deliberately not a second definition of the
state machine: it calls `claim`, `record_scan`, `record_derivative`, `mark_ready` and `confirm` in
their contracted order and asserts each one moved the row, so a transition that stops working fails
here as loudly as it does in `tests/privacy/test_record.py`.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import ClientError

from app.privacy import PROCESSING_VERSION, gate, record, redacted_key
from tests.api.conftest import _jpeg_bytes, auth_headers

#: A derivative's bytes: never the display object, because the two hashes must differ for
#: `lap_confirmed_ck` to mean anything about which one the seller saw.
REDACTED = b"redacted-bytes"
REDACTED_SHA = "c" * 64


async def _draft(client: Any, signed: dict[str, str]) -> str:
    response = await client.post("/api/seller/listings", headers=signed)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _submittable(client: Any, signed: dict[str, str], listing_id: str) -> None:
    """`tests/api/test_seller_listings.py::_submittable`'s own four steps — the least a listing can
    carry and still be submitted (`REQUIRED_TO_SUBMIT`, `listing_submittable_ck`)."""
    await client.patch(f"/api/seller/listings/{listing_id}?step=1",
                       json={"name": "Hill Country Animal Hospital", "type": "Small animal", "est": "1998"},
                       headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=2",
                       json={"city": "Cedar Park", "zip": "78613"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=3", json={"price": "1,450,000"}, headers=signed)
    await client.patch(f"/api/seller/listings/{listing_id}?step=4", json={"sqft": "3000"}, headers=signed)


async def _upload(client: Any, signed: dict[str, str], listing_id: str) -> UUID:
    response = await client.post(f"/api/seller/listings/{listing_id}/photos",
                                 files={"file": ("front.jpg", _jpeg_bytes(), "image/jpeg")}, headers=signed)
    assert response.status_code == 201, response.text
    return UUID(str(response.json()["id"]))


async def _listing_with_a_photograph(client: Any, signed: dict[str, str]) -> tuple[str, UUID]:
    """A submittable draft carrying one real photograph, through the real routes: a
    `listing_asset` row, a privacy row in UPLOADED, the original and the display object on the
    bucket, and one `media.process_photo` recorded by the `published_tasks` fixture."""
    listing_id = await _draft(client, signed)
    await _submittable(client, signed, listing_id)
    return listing_id, await _upload(client, signed, listing_id)


def _owner(conn: Any, listing_id: str) -> UUID:
    with conn.cursor() as cur:
        cur.execute("SELECT seller_id FROM listing WHERE id = %s", (listing_id,))
        return UUID(str(cur.fetchone()[0]))


def _visibility(conn: Any, listing_id: str, value: str) -> None:
    """The setting written NOT through the route — the starting state a flip test needs, and the
    only place in this module that writes the column without `patch_step`."""
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET identifiable_content_visibility = %s WHERE id = %s",
                    (value, listing_id))


def _pipelined(conn: Any, store: Any, listing_id: str, asset_id: UUID, *,
               visibility: str = "NOT_SHOW", confirm: bool = True, put: bool = True) -> str:
    """The row walked to READY_FOR_REVIEW, and on to SELLER_CONFIRMED, through `record`'s own
    writers — plus the derivative object on the bucket, because the flip verifies against the
    BUCKET and not only the row (spec C.1 step 3)."""
    key = redacted_key(listing_id, asset_id)
    assert record.claim(conn, asset_id, PROCESSING_VERSION) is not None
    record.record_scan(conn, asset_id, ocr={}, identity_matches=[], vision={}, detected_regions=[])
    record.record_derivative(conn, asset_id, key=key, sha256=REDACTED_SHA, regions=[])
    record.mark_ready(conn, asset_id, visible=visibility == "SHOW", version=PROCESSING_VERSION)
    if confirm:
        assert record.confirm(conn, asset_id, account_id=_owner(conn, listing_id),
                              visibility=visibility, edited=False)
    if put:
        store.put(key, REDACTED, "image/webp")
    return key


def _status(conn: Any, listing_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM listing WHERE id = %s", (listing_id,))
        return str(cur.fetchone()[0])


async def _publish(client: Any, staff: dict[str, str], listing_id: str) -> Any:
    return await client.post(f"/api/admin/listings/{listing_id}/decide",
                             json={"action": "publish", "state": "TX", "market": "Austin, TX"},
                             headers=staff)


def _staff(member: Any) -> dict[str, str]:
    _account, cookies, headers = member(roles=("staff",), email="idp-p10-staff@example.org")
    return auth_headers(cookies, headers)


# --- Scenario M: publish before processing completes (spec C.8, directive 11) --------------------


async def test_submit_refuses_while_a_photograph_has_not_finished_processing(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """Directive 11, at the seller's own door. The photograph has just been uploaded, so its row is
    UPLOADED and nothing about it has been decided — which is exactly the state a listing must not
    be published in."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    refused = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == {
        "code": "PHOTOS_NOT_READY",
        "message": gate.NOT_READY_MESSAGE["NOT_SHOW"],
        "photos": [{"id": str(asset_id), "status": "UPLOADED"}],
    }
    assert _status(conn, listing_id) == "draft"


async def test_the_refusal_under_show_carries_the_message_that_names_no_review(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """Spec H's two rows: under SHOW there is no confirmation in the way, so the message says
    processing alone. Neither string claims detection is certain (directive 23)."""
    listing_id, _asset_id = await _listing_with_a_photograph(client, seller)
    _visibility(conn, listing_id, "SHOW")
    refused = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)
    assert refused.status_code == 422
    assert refused.json()["error"]["message"] == gate.NOT_READY_MESSAGE["SHOW"]


async def test_under_not_show_a_reviewed_but_unconfirmed_photograph_still_refuses_submit(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """"Never allow AI_PASSED to mean READY_TO_PUBLISH" (directive 11 (3)). The pipeline has
    finished and the derivative exists; the seller has not said "Looks good", so the listing does
    not go out."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, confirm=False)
    refused = await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)
    assert refused.status_code == 422
    assert refused.json()["error"]["photos"] == [{"id": str(asset_id), "status": "READY_FOR_REVIEW"}]


async def test_the_admin_publish_decision_refuses_a_photograph_uploaded_after_the_submission(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """A-SL15 stands: an upload onto an in-review listing leaves it in review, and the reviewer's
    publish then waits for the new photograph (spec C.8). The queue row is real and the second
    photograph has never been near the pipeline."""
    listing_id, first = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, first)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    second = await _upload(client, seller, listing_id)
    refused = await _publish(client, _staff(member), listing_id)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == {
        "code": "PHOTOS_NOT_READY",
        "message": gate.NOT_READY_MESSAGE["NOT_SHOW"],
        "photos": [{"id": str(second), "status": "UPLOADED"}],
    }
    assert _status(conn, listing_id) == "in_review"


async def test_republish_refuses_while_a_confirmed_photograph_has_been_flagged_stale(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """Scenario M's last row. A flag is not a state (D-IDP-16): the listing was published and its
    photograph is still being served, and a NEW publication waits for the in-place re-run."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    assert (await _publish(client, _staff(member), listing_id)).status_code == 200
    assert (await client.post(f"/api/seller/listings/{listing_id}/status",
                              json={"action": "pause"}, headers=seller)).status_code == 200
    assert record.flag_stale(conn, listing_id=UUID(listing_id), reason="VERSION") == [asset_id]
    refused = await client.post(f"/api/seller/listings/{listing_id}/status",
                                json={"action": "republish"}, headers=seller)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["photos"] == [{"id": str(asset_id), "status": "STALE"}]
    assert _status(conn, listing_id) == "paused"


async def test_all_three_routes_pass_once_every_photograph_is_confirmed(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """The other half of the gate: it lets a ready listing through, and the publish stamps
    PUBLISHED on every photograph that was visible (spec C.4 — "published at least once", not
    reverted by a pause)."""
    staff = _staff(member)
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    assert (await _publish(client, staff, listing_id)).status_code == 200
    assert record.read(conn, asset_id).processing_status == "PUBLISHED"
    assert (await client.post(f"/api/seller/listings/{listing_id}/status",
                              json={"action": "pause"}, headers=seller)).status_code == 200
    assert record.read(conn, asset_id).processing_status == "PUBLISHED"
    republished = await client.post(f"/api/seller/listings/{listing_id}/status",
                                    json={"action": "republish"}, headers=seller)
    assert republished.status_code == 200, republished.text
    assert _status(conn, listing_id) == "published"
    assert record.read(conn, asset_id).processing_status == "PUBLISHED"


async def test_a_listing_with_no_photographs_publishes_exactly_as_it_did_before(
    client: Any, seller: dict[str, str], member: Any, conn: Any
) -> None:
    """The gate is about the photographs there ARE. Every listing published before this
    sub-project existed carries none, and none of them may be stopped by it."""
    listing_id = await _draft(client, seller)
    await _submittable(client, seller, listing_id)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    assert (await _publish(client, _staff(member), listing_id)).status_code == 200
    assert _status(conn, listing_id) == "published"


async def test_a_decline_is_never_gated_by_a_photographs_state(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """Only the publish branch asks. A reviewer must always be able to decline, and an unpublish is
    a listing LEAVING the market — the one direction a privacy gate has no business in."""
    listing_id, _asset_id = await _listing_with_a_photograph(client, seller)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing SET status = 'in_review', submitted_at = now() WHERE id = %s", (listing_id,))
    declined = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                 json={"action": "decline", "reason": "Not yet."}, headers=_staff(member))
    assert declined.status_code == 200, declined.text
    assert _status(conn, listing_id) == "declined"


# --- C.1 / directive 7: the listing setting, and its ONE writer ----------------------------------


def _column(conn: Any, listing_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT identifiable_content_visibility FROM listing WHERE id = %s", (listing_id,))
        return str(cur.fetchone()[0])


def _privacy_rows(conn: Any, listing_id: str) -> list[Any]:
    return record.rows_for(conn, UUID(listing_id))


def _audit(conn: Any, listing_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SELECT action, before, after, reason FROM audit_log"
                    " WHERE target_type = 'listing' AND target_id = %s ORDER BY id", (listing_id,))
        rows: list[tuple[Any, ...]] = cur.fetchall()
    return rows


async def _flip(client: Any, signed: dict[str, str], listing_id: str, *, show: bool) -> Any:
    return await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                              json={"showIdentifiable": show}, headers=signed)


async def test_a_new_listing_is_not_show_and_the_draft_says_so(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """John's ruling A-IDP-4: "Default → NOT SHOW, including all 18 seeds". The safest privacy
    state is the default, so the switch the seller meets is OFF and the column agrees."""
    listing_id = await _draft(client, seller)
    read = await client.get(f"/api/seller/listings/{listing_id}", headers=seller)
    assert read.json()["showIdentifiable"] is False
    assert _column(conn, listing_id) == "NOT_SHOW"


async def test_the_owner_step_seven_patch_is_the_one_writer_and_its_polarity_is_direct(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """NOT the inverted polarity of the three switches beside it. `anon`, `revBand` and
    `docsLocked` are "hide this"; John's control is "IDENTIFIABLE IMAGE CONTENT [ SHOW ]
    [ NOT SHOW ]", so ON means SHOW and the safe state is the switch at rest."""
    listing_id = await _draft(client, seller)
    shown = await _flip(client, seller, listing_id, show=True)
    assert shown.status_code == 200, shown.text
    assert shown.json()["showIdentifiable"] is True
    assert _column(conn, listing_id) == "SHOW"
    hidden = await _flip(client, seller, listing_id, show=False)
    assert hidden.json()["showIdentifiable"] is False
    assert _column(conn, listing_id) == "NOT_SHOW"


async def test_the_setting_is_a_boolean_and_nothing_else(client: Any, seller: dict[str, str], conn: Any) -> None:
    listing_id = await _draft(client, seller)
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step=7",
                                 json={"showIdentifiable": "SHOW"}, headers=seller)
    assert refused.status_code == 400
    assert refused.json()["error"]["message"] == "showIdentifiable must be true or false."
    assert _column(conn, listing_id) == "NOT_SHOW"


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
async def test_no_other_step_can_write_the_setting(
    client: Any, seller: dict[str, str], conn: Any, step: int
) -> None:
    """One writer means one door. D10's whitelist is one-directional and total, so the setting sent
    on any other step is a 400 rather than a silent second path to a privacy control."""
    listing_id = await _draft(client, seller)
    refused = await client.patch(f"/api/seller/listings/{listing_id}?step={step}",
                                 json={"showIdentifiable": True}, headers=seller)
    assert refused.status_code == 400
    assert "does not accept showIdentifiable" in refused.json()["error"]["message"]
    assert _column(conn, listing_id) == "NOT_SHOW"


async def test_the_reviewers_decision_cannot_write_the_setting(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """No admin route writes it (spec C.1). `Decision` is `extra="forbid"`, so the attempt is
    refused rather than ignored — and there is no admin PATCH for a listing at all."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id)
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    refused = await client.post(f"/api/admin/listings/{listing_id}/decide",
                                json={"action": "publish", "state": "TX", "market": "Austin, TX",
                                      "showIdentifiable": True}, headers=_staff(member))
    assert refused.status_code == 422, refused.text
    assert _column(conn, listing_id) == "NOT_SHOW"


async def test_every_change_writes_one_audit_row_that_carries_no_status_key(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """`_COLUMNS`' decline-reason subquery reads the latest `audit_log` row whose
    `after ->> 'status' = 'declined'`, so an action that wrote a `status` key would corrupt a
    seller's own "why was this declined" line."""
    listing_id = await _draft(client, seller)
    await _flip(client, seller, listing_id, show=True)
    assert _audit(conn, listing_id) == [
        ("listing.privacy",
         {"identifiable_content_visibility": "NOT_SHOW"},
         {"identifiable_content_visibility": "SHOW"},
         "visibility"),
    ]


async def test_a_patch_that_does_not_change_the_setting_records_nothing(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """The wizard's autosave PATCHes step 7 on every visit. A no-op write is not a change of a
    privacy control and must not read as one in the audit trail."""
    listing_id = await _draft(client, seller)
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    assert _audit(conn, listing_id) == []


async def test_a_flip_on_a_listing_with_no_photographs_needs_no_bucket(
    client: Any, seller: dict[str, str], conn: Any
) -> None:
    """The `store` fixture is deliberately absent. Every derivative of no photographs exists, so a
    listing with none is not held up by object storage the deployment may not have configured."""
    listing_id = await _draft(client, seller)
    assert (await _flip(client, seller, listing_id, show=True)).status_code == 200
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    assert _column(conn, listing_id) == "NOT_SHOW"


async def test_the_flip_drops_the_browse_cache_even_on_a_draft(
    client: Any, seller: dict[str, str], redis: Any, conn: Any
) -> None:
    """Unconditionally, unlike `patch_step`'s own `leaving_market` arm (spec C.1 (2)): the autosave
    is conditional because it fires 240 times an hour, and a privacy control moving is not that."""
    listing_id = await _draft(client, seller)
    redis.set("listings:v1:abc", "cached")
    assert (await _flip(client, seller, listing_id, show=True)).status_code == 200
    assert redis.keys("listings:v1:*") == []


# --- Directive 16, SHOW -> NOT_SHOW: verify against the BUCKET, not only the row -----------------


async def test_a_row_confirmed_under_not_show_against_its_own_derivative_keeps_its_state(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """Spec C.1 step 3's "keeps its state": `lap_confirmed_ck` holds
    `confirmed_sha256 = redacted_sha256`, so the seller has already approved exactly the bytes a
    buyer would now be served. Nothing is re-run and nothing is re-reviewed."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "SELLER_CONFIRMED" and row.seller_confirmed is True
    assert row.buyer_visible is True
    assert published_tasks == []


async def test_a_row_confirmed_under_show_goes_back_to_review_with_its_confirmation_reset(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """The seller approved this photograph as a SHOW listing's — they have never been asked whether
    the redacted derivative is good enough. Directive 11 (3) says they must be."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="SHOW")
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "READY_FOR_REVIEW"
    assert row.seller_confirmed is False and row.confirmed_sha256 is None
    assert row.buyer_visible is False
    assert row.redacted_storage_key is not None, "nothing is deleted; the derivative is still there"
    assert published_tasks == []


async def test_a_derivative_whose_object_has_gone_is_cleared_and_re_processed(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """§16's "immediately require/verify that redacted derivatives exist for EVERY image", done
    against the BUCKET: a row claiming a derivative it cannot serve is a row that would answer a
    buyer with nothing, so it loses the claim and starts again."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    key = _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    store.delete(key)
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "UPLOADED" and row.attempts == 0
    assert row.redacted_storage_key is None and row.redacted_sha256 is None
    assert row.seller_confirmed is False and row.buyer_visible is False
    assert published_tasks == [("media.process_photo", [str(asset_id), PROCESSING_VERSION])]


async def test_a_photograph_that_never_finished_processing_is_re_enqueued_by_the_flip(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """`redacted_storage_key IS NULL` — the row has no derivative to verify at all, so there is
    nothing for the existence pass to ask about and the answer is the same: run the pipeline."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    assert record.read(conn, asset_id).processing_status == "UPLOADED"
    assert published_tasks == [("media.process_photo", [str(asset_id), PROCESSING_VERSION])]


async def test_a_failed_row_with_a_stale_derivative_is_re_processed_and_never_promoted(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """The SHOW -> NOT_SHOW flip's third arm. A REDACTION_FAILED row may still carry a
    `redacted_storage_key` whose object is on the bucket -- the CHECK permits it -- so the
    existence pass lets it through, and only `reset_confirmation`'s own READY_STATES guard stops it
    becoming reviewable, then confirmable, then visible over a derivative that failed."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="SHOW", confirm=False)
    with conn.cursor() as cur:
        cur.execute("UPDATE listing_asset_privacy SET processing_status = 'REDACTION_FAILED',"
                    " buyer_visible = false, attempts = 2 WHERE asset_id = %s", (asset_id,))
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "UPLOADED" and row.redacted_storage_key is None
    assert row.attempts == 0
    assert row.buyer_visible is False and row.seller_confirmed is False
    assert published_tasks == [("media.process_photo", [str(asset_id), PROCESSING_VERSION])]


async def test_a_bucket_outage_during_a_flip_is_a_503_and_changes_nothing(
    client: Any, seller: dict[str, str], store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch,
    published_tasks: list[Any],
) -> None:
    """Spec C.1 step 3 refuses rather than skipping the check, and that has to hold for a bucket
    that ERRORS as well as for one that is unconfigured -- `ObjectStore.exists` re-raises anything
    that is not a 404."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    _visibility(conn, listing_id, "SHOW")
    before = record.read(conn, asset_id)
    published_tasks.clear()

    def _raise(self: Any, key: str) -> bool:
        raise ClientError({"Error": {"Code": "InternalError"}}, "HeadObject")

    monkeypatch.setattr("app.api.seller_listings.ObjectStore.exists", _raise)
    refused = await _flip(client, seller, listing_id, show=False)
    assert refused.status_code == 503 and refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert record.read(conn, asset_id) == before
    assert _column(conn, listing_id) == "SHOW", "the setting itself is rolled back with the rest"
    assert published_tasks == []


async def test_a_flip_on_a_listing_with_photographs_refuses_when_no_bucket_is_configured(
    client: Any, seller: dict[str, str], store: Any, conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"a flip on a listing with photographs refuses rather than skips the check" (spec C.1 step
    3). Unconfigured storage is not permission to assume every derivative is there."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    _visibility(conn, listing_id, "SHOW")
    monkeypatch.setattr("app.config.settings.s3_bucket", None)
    refused = await _flip(client, seller, listing_id, show=False)
    assert refused.status_code == 503 and refused.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert _column(conn, listing_id) == "SHOW"


# --- Directive 16, NOT_SHOW -> SHOW: nothing is deleted and every confirmation stands ------------


async def test_the_flip_to_show_deletes_nothing_and_keeps_every_confirmation(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """"Retain them for future switching back" (§16), which is what makes switching back cost no
    reprocessing: the confirmation stands as recorded and the flip home finds it."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    key = _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=True)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "SELLER_CONFIRMED" and row.seller_confirmed is True
    assert row.buyer_visible is True
    assert store.exists(key), "nothing is deleted"
    assert published_tasks == []
    # ...and the round trip needs no pipeline run at all.
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    assert record.read(conn, asset_id).processing_status == "SELLER_CONFIRMED"
    assert published_tasks == []


async def test_the_flip_to_show_gives_visibility_to_readiness_alone(
    client: Any, seller: dict[str, str], store: Any, conn: Any
) -> None:
    """Spec C.1 step 4: under SHOW the display object is the served representation and no
    confirmation stands between a ready photograph and a buyer — but a photograph that has not
    finished is still nobody's."""
    listing_id, ready = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, ready, visibility="NOT_SHOW", confirm=False)
    unfinished = await _upload(client, seller, listing_id)
    assert (await _flip(client, seller, listing_id, show=True)).status_code == 200
    assert record.read(conn, ready).buyer_visible is True
    assert record.read(conn, unfinished).buyer_visible is False


async def test_a_flip_on_a_published_listing_still_re_enters_review(
    client: Any, seller: dict[str, str], member: Any, store: Any, conn: Any
) -> None:
    """Spec C.1 (5): the existing D3 arm is untouched. A flip is an edit buyers must not see until
    it has been through review, so §16's "block publication" is structural and the gate decides the
    re-publish."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    assert (await client.post(f"/api/seller/listings/{listing_id}/submit", headers=seller)).status_code == 200
    assert (await _publish(client, _staff(member), listing_id)).status_code == 200
    assert (await _flip(client, seller, listing_id, show=True)).status_code == 200
    assert _status(conn, listing_id) == "in_review"


async def test_a_stale_flag_does_not_survive_the_re_processing_the_flip_orders(
    client: Any, seller: dict[str, str], store: Any, conn: Any, published_tasks: list[Any]
) -> None:
    """A row can be BOTH flagged for an in-place re-run and missing the derivative that re-run was
    going to replace (`reprocess_reason` is a flag and not a state, D-IDP-16). The flip sends it
    back to UPLOADED for a FRESH run, and a fresh run is not the in-place one: `advance_in_place`
    is the only writer that clears the flag, and nothing on the `claim` -> `mark_ready` path ever
    reaches it. Left standing, the flag would make the listing permanently unpublishable — the
    gate's STALE arm fires on any row that carries one — and it would name the same photograph
    TWICE in one refusal."""
    listing_id, asset_id = await _listing_with_a_photograph(client, seller)
    key = _pipelined(conn, store, listing_id, asset_id, visibility="NOT_SHOW")
    assert record.flag_stale(conn, listing_id=UUID(listing_id), reason="VERSION") == [asset_id]
    store.delete(key)
    _visibility(conn, listing_id, "SHOW")
    published_tasks.clear()
    assert (await _flip(client, seller, listing_id, show=False)).status_code == 200
    row = record.read(conn, asset_id)
    assert row.processing_status == "UPLOADED" and row.reprocess_reason is None
    assert gate.photos_not_ready(conn, UUID(listing_id)) == [(str(asset_id), "UPLOADED")]
    assert published_tasks == [("media.process_photo", [str(asset_id), PROCESSING_VERSION])]
