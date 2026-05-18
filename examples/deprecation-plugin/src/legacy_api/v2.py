# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""v2 endpoints — current API surface.

This module also illustrates the *comment-style* marker the scanner
accepts. Both forms work; pick whichever fits the language better
(comment style is the only option for non-Python files like JSON / YAML
templates / Helm values)."""

from __future__ import annotations


# DEPRECATED since=1.2.0 remove_in=3.0.0 — body kwarg is going away,
# pass ``payload`` instead.
def new_endpoint(payload: dict, *, body: dict | None = None) -> dict:
    """Returns the v2 response shape. The ``body`` kwarg is staged for
    removal in 3.0.0 — surfaces as an "upcoming" line in
    ``multicz status`` until the release window catches up with it."""
    return {"version": 2, **(body or payload)}
