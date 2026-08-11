"""Pytest / Hypothesis configuration for nuropb-rmq tests."""

from __future__ import annotations

import os

from hypothesis import settings


def pytest_configure() -> None:
    settings.register_profile("default", max_examples=50)
    settings.register_profile("ci", max_examples=200, deadline=None)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
