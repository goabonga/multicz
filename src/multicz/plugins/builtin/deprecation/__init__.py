# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Built-in deprecation-policy plugin.

Detects deprecation markers in component sources and enforces a
"remove by version N" policy at bump time. Also contributes
``Deprecated`` / ``Removed`` sections to changelogs and release notes
when relevant.

See :mod:`multicz.plugins.builtin.deprecation.plugin` for the public
:class:`DeprecationPlugin` entry point.
"""

from .plugin import DeprecationPlugin

__all__ = ["DeprecationPlugin"]
