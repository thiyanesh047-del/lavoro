"""Shared test helpers. Tests never touch data/lavoro.db, the network or Claude."""
from __future__ import annotations

import pytest

from lavoro import db


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def job(key: str, **kw) -> dict:
    """A job as the board fetchers return it."""
    base = dict(key=key, source=key.split(":", 1)[0], company="Acme", title="Product Designer", location="Stockholm, Sweden",
                remote=False, department="Design", url=f"https://example.com/{key}", salary=None,
                description="We are looking for a product designer.", posted_at=None)
    return {**base, **kw}
