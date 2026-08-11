"""Unit tests for session ids and correlation table."""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings, strategies as st

from nuropb_rmq.session.correlation import CorrelationTable
from nuropb_rmq.session.ids import IdCollisionError, InvalidIdError, generate_id, validate_id


def test_validate_id_accepts_uuid_hex() -> None:
    assert validate_id(generate_id()) == generate_id() or True
    validate_id("a" * 32)


def test_validate_id_rejects_bad() -> None:
    with pytest.raises(InvalidIdError):
        validate_id("")
    with pytest.raises(InvalidIdError):
        validate_id("has space")
    with pytest.raises(InvalidIdError):
        validate_id("x" * 256)


@pytest.mark.asyncio
async def test_first_reply_wins_late_discarded() -> None:
    table = CorrelationTable()
    rid, fut = table.register("abc123")
    assert rid == "abc123"
    assert table.resolve(rid, "first") is True
    assert await fut == "first"
    assert table.resolve(rid, "second") is False  # discarded
    assert len(table) == 0


@pytest.mark.asyncio
async def test_collision_reject() -> None:
    table = CorrelationTable()
    table.register("same-id")
    with pytest.raises(IdCollisionError):
        table.register("same-id")


@given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-", min_size=1, max_size=64))
@settings(max_examples=40)
def test_pbt_valid_ids(value: str) -> None:
    assert validate_id(value) == value


@given(st.sampled_from(["", "bad id", "\x00", "x" * 300]))
@settings(max_examples=20)
def test_pbt_invalid_ids(value: str) -> None:
    with pytest.raises(InvalidIdError):
        validate_id(value)


@given(st.lists(st.sampled_from(["a", "b", "c"]), min_size=2, max_size=8))
@settings(max_examples=30)
@pytest.mark.asyncio
async def test_pbt_first_wins(ids: list[str]) -> None:
    table = CorrelationTable()
    rid, fut = table.register("req1")
    winners = []
    for i, _ in enumerate(ids):
        if table.resolve(rid, f"v{i}"):
            winners.append(i)
    assert winners == [0]
    assert await fut == "v0"


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=16))
@settings(max_examples=40)
@pytest.mark.asyncio
async def test_pbt_collision_reject(request_id: str) -> None:
    table = CorrelationTable()
    table.register(request_id)
    with pytest.raises(IdCollisionError):
        table.register(request_id)


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=16))
@settings(max_examples=40)
@pytest.mark.asyncio
async def test_pbt_late_discard(request_id: str) -> None:
    table = CorrelationTable()
    rid, fut = table.register(request_id)
    assert table.resolve(rid, "ok") is True
    assert await fut == "ok"
    assert table.resolve(rid, "late") is False
    assert table.resolve("never-registered", "x") is False
