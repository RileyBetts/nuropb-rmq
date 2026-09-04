# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Correspondence for Lean ``tryDedup`` and RpcServer success cache."""

from __future__ import annotations

import pytest

from nuropb_rmq.patterns.rpc import try_dedup


def test_try_dedup_fresh_then_replay() -> None:
    out, seen = try_dedup([], 2, "abc")
    assert out == "fresh"
    assert seen == ["abc"]
    out2, seen2 = try_dedup(seen, 2, "abc")
    assert out2 == "replay"
    assert seen2 == seen


def test_try_dedup_off_never_inserts() -> None:
    out, seen = try_dedup(["x"], 0, "abc")
    assert out == "fresh"
    assert seen == ["x"]


def test_try_dedup_evicts_oldest() -> None:
    seen = ["b", "a"]
    out, seen = try_dedup(seen, 2, "c")
    assert out == "fresh"
    assert seen == ["c", "b"]
    out2, _ = try_dedup(seen, 2, "a")
    assert out2 == "fresh"


def test_rpc_server_rejects_negative_window() -> None:
    from nuropb_rmq.patterns.rpc import RpcServer

    with pytest.raises(ValueError, match="dedup_window"):
        RpcServer(queue="q", handler=lambda m, p: {}, dedup_window=-1)
