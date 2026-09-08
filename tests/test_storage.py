"""ObjectStore -- one generic S3-compatible adapter for the whole programme (controller
amendment A-C2 P1): the Census raw-payload archive keys everything under `census/`
(spec S10, an immutable audit record -- immutability is the CALLER's discipline, never
this class's) and the seller-lifecycle photo/document uploads key everything under
`listings/`, where overwriting on re-upload is exactly the point. `put` therefore always
writes; there is no `put_immutable` here.

Tests run entirely against moto (`mock_aws`); no network call is made.
"""
from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.config import Settings
from app.storage import ObjectStore


@pytest.fixture
def store():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="pm-test")
        yield ObjectStore(endpoint_url=None, bucket="pm-test", access_key="x", secret_key="y", region="us-east-1")


def test_put_then_get_round_trips(store):
    store.put("census/acs5/2019-2023/abc.json", b'{"a": 1}', "application/json")
    assert store.get("census/acs5/2019-2023/abc.json") == b'{"a": 1}'


def test_put_overwrites_an_existing_key(store):
    store.put("listings/l1/photo.jpg", b"one", "image/jpeg")
    store.put("listings/l1/photo.jpg", b"two", "image/jpeg")
    assert store.get("listings/l1/photo.jpg") == b"two"


def test_get_missing_returns_none(store):
    assert store.get("nope") is None


def test_exists_false_before_put_true_after(store):
    assert store.exists("k") is False
    store.put("k", b"v", "text/plain")
    assert store.exists("k") is True


def test_delete_removes_the_object(store):
    store.put("k", b"v", "text/plain")
    store.delete("k")
    assert store.exists("k") is False
    assert store.get("k") is None


def test_list_returns_keys_under_a_prefix_only(store):
    store.put("listings/l1/a.jpg", b"a", "image/jpeg")
    store.put("listings/l1/b.jpg", b"b", "image/jpeg")
    store.put("census/other.json", b"{}", "application/json")
    assert sorted(store.list("listings/l1/")) == ["listings/l1/a.jpg", "listings/l1/b.jpg"]


def test_list_returns_empty_for_no_matches(store):
    assert store.list("nothing/here/") == []


def test_exists_reraises_non_404_client_errors():
    with mock_aws():
        store = ObjectStore(endpoint_url=None, bucket="does-not-exist", access_key="x", secret_key="y", region="us-east-1")
        with pytest.raises(ClientError):
            store.exists("k")


def test_get_reraises_non_404_client_errors():
    with mock_aws():
        store = ObjectStore(endpoint_url=None, bucket="does-not-exist", access_key="x", secret_key="y", region="us-east-1")
        with pytest.raises(ClientError):
            store.get("k")


def test_from_settings_is_none_when_unconfigured():
    s = Settings(database_url="postgresql://x", redis_url="redis://x", environment="test", api_secret_key="x")
    assert ObjectStore.from_settings(s) is None


def test_from_settings_is_none_when_only_some_of_the_four_s3_settings_are_present():
    s = Settings(
        database_url="postgresql://x", redis_url="redis://x", environment="test", api_secret_key="x",
        s3_bucket="practice-match-data", s3_access_key_id="AKIA", s3_secret_access_key="secret",
    )
    assert ObjectStore.from_settings(s) is None


def test_from_settings_returns_a_real_client_when_all_four_are_present():
    s = Settings(
        database_url="postgresql://x", redis_url="redis://x", environment="test", api_secret_key="x",
        s3_endpoint_url="https://s3.example.railway.app", s3_bucket="practice-match-data",
        s3_access_key_id="AKIA", s3_secret_access_key="secret",
    )
    store = ObjectStore.from_settings(s)
    assert isinstance(store, ObjectStore)
    assert store.bucket == "practice-match-data"
