# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""legacy_api — example package that exercises the deprecation plugin.

Two markers live in this package, each chosen to demonstrate one of the
plugin's three states at the same time:

* :mod:`.v1` — past-due marker. ``remove_in=2.0.0`` means a planned
  bump to ``2.0.0`` triggers a ``post_plan`` violation and aborts the
  bump until ``old_endpoint`` is actually removed.
* :mod:`.v2` — upcoming marker. ``remove_in=3.0.0`` only shows up in
  the ``multicz status`` advice line ("1 upcoming") and contributes a
  ``Deprecated`` section to the changelog the first time it lands
  inside a release window.

Together they let the example show every behaviour of the plugin
without needing more than a single component.
"""

from .v1 import old_endpoint
from .v2 import new_endpoint

__all__ = ["old_endpoint", "new_endpoint"]
