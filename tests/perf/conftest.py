"""Fixtures the listings budgets need (Task L5).

`member` is imported from tests/api/conftest.py rather than re-implemented, and `client` is
DELIBERATELY not imported: the root conftest's `client` (a tmp_path `dist`, base URL
http://test) is what the existing `/api/healthz` and `/` budgets measure, and shadowing it
here would silently change what those two tests are timing. The listings budgets build their
own client against the site's real origin instead.
"""
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from tests.api.conftest import ORIGIN, member

__all__ = ["ORIGIN", "member", "origin_client"]


@pytest.fixture
async def origin_client(redis: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url=ORIGIN) as c:
        yield c
