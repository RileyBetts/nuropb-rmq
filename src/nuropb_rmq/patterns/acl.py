# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Nuropb broker ACL profiles (correspondence with Lean ``Pattern.Acl``).

Prefix matchers for the documented ``reply-publish-restricted`` and
``mesh-bind-namespaced`` shapes, plus a scoped ``matches_regex`` for the same
profiles rewritten as regex. This is not RabbitMQ's full regex engine / HA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def matches_prefix(pattern: str, name: str) -> bool:
    return name == pattern or name.startswith(pattern)


def matches_regex(pattern: str, name: str) -> bool:
    """Scoped regex used for documented profiles. Bad pattern → False."""
    try:
        return re.search(pattern, name) is not None
    except re.error:
        return False


def allowed(patterns: tuple[str, ...] | list[str], name: str) -> bool:
    return any(matches_prefix(p, name) for p in patterns)


def allowed_regex(patterns: tuple[str, ...] | list[str], name: str) -> bool:
    return any(matches_regex(p, name) for p in patterns)


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

    def can_configure_regex(self, name: str) -> bool:
        return allowed_regex(self.configure, name)

    def can_publish_regex(self, name: str) -> bool:
        return allowed_regex(self.write, name)

    def can_read_regex(self, name: str) -> bool:
        return allowed_regex(self.read, name)


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


# Documented profiles rewritten as regex (same golden names as prefixes).
REPLY_PUBLISH_RESTRICTED_CLIENT_RE = Perms(
    configure=(r"^nr\.reply\.",),
    write=(r"^nr\.mesh",),
    read=(r"^nr\.reply\.",),
)

REPLY_PUBLISH_RESTRICTED_SERVICE_RE = Perms(
    configure=(r"^nr\.svc\.", r"^nr\.reply\."),
    write=(r"^nr\.mesh", r"^nr\.reply\.", r"^nr\.dlx\."),
    read=(r"^nr\.svc\.", r"^nr\.mesh", r"^nr\.dlx\."),
)

REPLY_HEX8 = r"^nr\.reply\.[0-9a-f]{8}"


def mesh_bind_namespaced_re(service: str) -> Perms:
    return Perms(
        configure=(rf"^{re.escape(service)}",),
        write=(rf"^{re.escape(service)}", r"^nr\.mesh"),
        read=(rf"^{re.escape(service)}", r"^nr\.mesh"),
    )
