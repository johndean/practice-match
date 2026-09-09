"""Read side of dataset_registry. Attribution strings and licence status come from
the database (spec §12) so a terms change propagates in one UPDATE."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg2.extensions

COLUMNS = ("dataset_key", "display_name", "api_dataset_id", "base_url", "vintage", "naics_param", "refresh_cadence",
           "license_status", "license_name", "license_url", "attribution_text", "last_verified_at", "notes")


@dataclass(frozen=True)
class Dataset:
    dataset_key: str
    display_name: str
    api_dataset_id: str | None
    base_url: str
    vintage: str
    naics_param: str | None
    refresh_cadence: str
    license_status: str
    license_name: str | None
    license_url: str | None
    attribution_text: str
    last_verified_at: datetime | None
    notes: str | None

    @property
    def cleared(self) -> bool:
        return self.license_status == "cleared"


def load(conn: psycopg2.extensions.connection) -> dict[str, Dataset]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(COLUMNS)} FROM dataset_registry ORDER BY dataset_key")
        return {row[0]: Dataset(*row) for row in cur.fetchall()}


def is_cleared(conn: psycopg2.extensions.connection, dataset_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT license_status = 'cleared' FROM dataset_registry WHERE dataset_key = %s", (dataset_key,))
        row = cur.fetchone()
        return bool(row and row[0])


def attribution(conn: psycopg2.extensions.connection, dataset_keys: list[str]) -> list[str]:
    """Attribution lines in the order requested; unknown keys are skipped, not invented."""
    if not dataset_keys:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, attribution_text FROM dataset_registry WHERE dataset_key = ANY(%s)", (dataset_keys,))
        by_key = dict(cur.fetchall())
    return [by_key[k] for k in dataset_keys if k in by_key]
