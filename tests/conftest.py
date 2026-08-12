# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Pytest / Hypothesis configuration for nuropb-rmq tests."""

from __future__ import annotations

import os

from hypothesis import settings


def pytest_configure() -> None:
    settings.register_profile("default", max_examples=50)
    settings.register_profile("ci", max_examples=200, deadline=None)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
