# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from multicz.validation._base import Finding


def test_finding_to_dict():
    finding = Finding(level="warning", check="c", component="api", message="m")
    assert finding.to_dict() == {
        "level": "warning",
        "check": "c",
        "component": "api",
        "message": "m",
    }
