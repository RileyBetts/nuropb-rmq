# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Write hex golden vectors for the Lean oracle. Not a public API."""

from __future__ import annotations

from pathlib import Path

from nuropb_rmq.protocol.methods import (
    BASIC,
    BASIC_ACK,
    CONNECTION,
    CONNECTION_TUNE_OK,
    Method,
    encode_method,
)
from nuropb_rmq.transport.frame import Frame, FrameType, encode_frame

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "specs" / "vectors"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[str, bytes]] = []
    hb = bytes(encode_frame(Frame(FrameType.HEARTBEAT, 0, b"")))
    frames.append(("heartbeat", hb))
    method = encode_method(
        Method(CONNECTION, CONNECTION_TUNE_OK, {"channel_max": 2047, "frame_max": 131072, "heartbeat": 60})
    )
    frames.append(("tune_ok", bytes(encode_frame(Frame(FrameType.METHOD, 0, method)))))
    ack = encode_method(Method(BASIC, BASIC_ACK, {"delivery_tag": 1, "multiple": False}))
    frames.append(("basic_ack", bytes(encode_frame(Frame(FrameType.METHOD, 1, ack)))))
    (OUT / "frames.txt").write_text(
        "".join(f"{name} {raw.hex()}\n" for name, raw in frames),
        encoding="utf-8",
    )
    (OUT / "sm_trace.txt").write_text(
        "\n".join(
            [
                "tcpConnected:false",
                "amqpHeader",
                "connStart",
                "startOk",
                "tune",
                "tuneOk:60",
                "open",
                "openOk",
                "final:openOk",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (OUT / "acl.txt").write_text(
        "tryBind orders orders.ping bindOk\ntryBind orders payments.charge bindRefused\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
