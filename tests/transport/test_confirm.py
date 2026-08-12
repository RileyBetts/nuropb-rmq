# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Publisher confirm tracker unit / PBT tests."""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.transport.confirm import ConfirmTracker, PublishNack


@pytest.mark.asyncio
async def test_ack_resolves_future() -> None:
    t = ConfirmTracker()
    t.enable()
    tag, fut = t.register()
    assert tag == 1
    t.on_ack(1, multiple=False)
    await fut


@pytest.mark.asyncio
async def test_nack_raises() -> None:
    t = ConfirmTracker()
    t.enable()
    _tag, fut = t.register()
    t.on_nack(1, multiple=False)
    with pytest.raises(PublishNack):
        await fut


@pytest.mark.asyncio
async def test_multiple_ack() -> None:
    t = ConfirmTracker()
    t.enable()
    _, f1 = t.register()
    _, f2 = t.register()
    _, f3 = t.register()
    t.on_ack(2, multiple=True)
    await f1
    await f2
    assert not f3.done()
    t.on_ack(3, multiple=False)
    await f3


@given(st.lists(st.sampled_from(["ack", "nack"]), min_size=1, max_size=20))
@settings(max_examples=40, deadline=None)
def test_pbt_confirm_sequences(ops: list[str]) -> None:
    async def _run() -> None:
        t = ConfirmTracker()
        t.enable()
        futs = []
        for _ in ops:
            futs.append(t.register()[1])
        for i, op in enumerate(ops):
            tag = i + 1
            if op == "ack":
                t.on_ack(tag, multiple=False)
                await futs[i]
            else:
                t.on_nack(tag, multiple=False)
                with pytest.raises(PublishNack):
                    await futs[i]

    asyncio.run(_run())
