# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Nuropb broker ACL profiles (correspondence with Lean ``Pattern.Acl``).

Prefix matchers for the documented ``reply-publish-restricted`` and
``mesh-bind-namespaced`` shapes. This is not RabbitMQ's regex engine.
"""

from __future__ import annotations

from dataclasses import dataclass


def matches_prefix(pattern: str, name: str) -> bool:
    return name == pattern or name.startswith(pattern)


def allowed(patterns: tuple[str, ...] | list[str], name: str) -> bool:
    return any(matches_prefix(p, name) for p in patterns)


@dataclass(frozen=True, slots=True)
class Perms:
    configure: tuple[str, ...]
    write: tuple[str, ...]
    read: tuple[str, ...]

    def can_configure(self, name: str) -> bool:
        return allowed(self.configure, name)

    def can_publish(self, name: str) -> bool:
        return allowed(self.write, name)

    def can_read(self, name: str) -> bool:
        return allowed(self.read, name)


# Client: declare/consume own reply queues; publish mesh only — not nr.reply.*
REPLY_PUBLISH_RESTRICTED_CLIENT = Perms(
    configure=("nr.reply.",),
    write=("nr.mesh",),
    read=("nr.reply.",),
)

REPLY_PUBLISH_RESTRICTED_SERVICE = Perms(
    configure=("nr.svc.", "nr.reply."),
    write=("nr.mesh", "nr.reply.", "nr.dlx."),
    read=("nr.svc.", "nr.mesh", "nr.dlx."),
)


def mesh_bind_namespaced(service: str) -> Perms:
    return Perms(
        configure=(service,),
        write=(service, "nr.mesh"),
        read=(service, "nr.mesh"),
    )
