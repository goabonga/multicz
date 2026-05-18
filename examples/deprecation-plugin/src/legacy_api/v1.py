# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""v1 endpoints — kept around for backwards compatibility until 2.0.0.

The decorator below is what the plugin scans for. Both the ``since`` and
``remove_in`` kwargs are required; the scanner is order-insensitive."""

from __future__ import annotations


def deprecated(*, since: str, remove_in: str, message: str = ""):
    """No-op decorator the scanner can match on.

    A real project would use ``warnings.warn(..., DeprecationWarning)``
    inside the wrapper — what matters for multicz is only the literal
    ``@deprecated(since=..., remove_in=...)`` line on the function above
    the implementation."""

    def _wrap(fn):
        return fn

    return _wrap


@deprecated(since="1.0.0", remove_in="2.0.0", message="use new_endpoint")
def old_endpoint(payload: dict) -> dict:
    """Returns the v1 response shape. Slated for removal in 2.0.0."""
    return {"version": 1, **payload}
