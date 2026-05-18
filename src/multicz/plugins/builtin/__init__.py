# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Built-in multicz plugins shipped alongside the core.

Each built-in lives in its own submodule and registers via
``[project.entry-points."multicz.plugins"]`` in multicz's pyproject.toml
— same path third-party plugins use, so there's no privileged loader.
"""
