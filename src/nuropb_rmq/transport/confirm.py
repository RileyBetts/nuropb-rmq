"""Publisher confirm tracking (RabbitMQ confirm.select extension)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


class PublishNack(Exception):
    """Broker nack'd a confirmed publish."""

    def __init__(self, delivery_tag: int, *, multiple: bool = False) -> None:
        self.delivery_tag = delivery_tag
        self.multiple = multiple
        super().__init__(f"publish nack delivery_tag={delivery_tag} multiple={multiple}")


@dataclass
class ConfirmTracker:
    """Per-channel outstanding publish confirms.

    SpeC++/Lean: a confirm-mode publish is incomplete until ack or nack;
    ``multiple`` resolves all outstanding tags ≤ delivery_tag; first resolution wins.
    """

    next_tag: int = 1
    outstanding: dict[int, asyncio.Future[None]] = field(default_factory=dict)
    enabled: bool = False

    def enable(self) -> None:
        self.enabled = True
        self.next_tag = 1

    def register(self) -> tuple[int, asyncio.Future[None]]:
        if not self.enabled:
            raise RuntimeError("confirm mode not enabled")
        tag = self.next_tag
        self.next_tag += 1
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.outstanding[tag] = fut
        return tag, fut

    def on_ack(self, delivery_tag: int, *, multiple: bool) -> None:
        self._resolve(delivery_tag, multiple=multiple, exc=None)

    def on_nack(self, delivery_tag: int, *, multiple: bool) -> None:
        self._resolve(
            delivery_tag,
            multiple=multiple,
            exc=PublishNack(delivery_tag, multiple=multiple),
        )

    def _resolve(
        self, delivery_tag: int, *, multiple: bool, exc: BaseException | None
    ) -> None:
        if multiple:
            tags = sorted(t for t in self.outstanding if t <= delivery_tag)
        else:
            tags = [delivery_tag] if delivery_tag in self.outstanding else []
        for tag in tags:
            fut = self.outstanding.pop(tag, None)
            if fut is None or fut.done():
                continue
            if exc is None:
                fut.set_result(None)
            else:
                fut.set_exception(exc)

    def fail_all(self, exc: BaseException) -> None:
        for fut in list(self.outstanding.values()):
            if not fut.done():
                fut.set_exception(exc)
        self.outstanding.clear()
