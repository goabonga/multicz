# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Helm chart name reading on an unparseable chart."""

from pathlib import Path

from multicz.discovery.helm import _read_chart_name


def test_read_chart_name_unparseable(tmp_path: Path) -> None:
    path = tmp_path / "Chart.yaml"
    path.write_text("name: [unclosed\n")
    assert _read_chart_name(path) is None
