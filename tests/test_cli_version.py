# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from typer.testing import CliRunner

from multicz import __version__
from multicz.cli import app


def test_version_flag_prints_the_version_and_exits() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"multicz {__version__}" in result.output
