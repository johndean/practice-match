"""Generic object storage on a Railway bucket (S3-compatible). One adapter for the whole
programme (controller amendment A-C2 P1): the Census raw-payload archive keys everything
under `census/` (spec S10 -- an immutable audit record of what was received, kept forever)
and the seller-lifecycle photo/document uploads key everything under `listings/`, where
overwriting on a re-upload is exactly what is wanted. This class makes no assumption about
which: `put` always writes. Archive immutability, where it matters, is the CALLER's
discipline -- check `exists()` before calling `put()` -- not this module's.

`from_settings()` is the boot-time seam: it returns a configured client only when all four
`S3_*` settings are present (A-C2 P2), and `None` otherwise, so a service without bucket
credentials degrades -- an unconfigured archive, a disabled upload path -- instead of
crashing. The api never strictly needs it today; the worker does.
"""
from __future__ import annotations

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings

log = logging.getLogger(__name__)

_NOT_FOUND_CODES = ("404", "NoSuchKey", "NotFound")
#: m6 (controller amendment A-C11 (7)): `list_objects_v2` truncates at this many keys per call and
#: reports `IsTruncated`/`NextContinuationToken` when there is more -- `list()` below follows the
#: token across pages rather than silently returning only the first one. A module-level constant
#: (not a `list()` parameter) so a caller never has to think about it, and a test can monkeypatch
#: it down to force real multi-page moto behaviour without waiting on 1 000+ fixture objects.
_LIST_PAGE_SIZE = 1000


class ObjectStore:
    def __init__(self, endpoint_url: str | None, bucket: str, access_key: str, secret_key: str, region: str = "auto") -> None:
        self.bucket = bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ObjectStore | None:
        if not (settings.s3_endpoint_url and settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
            log.warning("[storage] S3 bucket not fully configured -- object store disabled")
            return None
        return cls(settings.s3_endpoint_url, settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key)

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                return False
            raise

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        try:
            return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                return None
            raise

    def delete(self, key: str) -> bool:
        """Removes `key`, reporting whether it was actually there to remove (A-SL1): S3's
        `delete_object` succeeds unconditionally on a key that never existed, so the caller
        would otherwise have no way to tell a real deletion from a no-op."""
        existed = self.exists(key)
        self._s3.delete_object(Bucket=self.bucket, Key=key)
        return existed

    def list(self, prefix: str) -> list[str]:
        """Follows `NextContinuationToken` across every page (m6, A-C11 (7)) -- a single call
        silently truncated at `_LIST_PAGE_SIZE` keys, which is exactly the failure mode a caller
        with more objects than that under one prefix would hit with no error at all."""
        keys: list[str] = []
        token: str | None = None
        while True:
            resp = (
                self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=_LIST_PAGE_SIZE, ContinuationToken=token)
                if token is not None
                else self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=_LIST_PAGE_SIZE)
            )
            keys.extend(obj["Key"] for obj in resp.get("Contents", []))
            if not resp.get("IsTruncated"):
                return keys
            token = resp["NextContinuationToken"]
