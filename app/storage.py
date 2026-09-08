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

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self.bucket, Key=key)

    def list(self, prefix: str) -> list[str]:
        resp = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]
