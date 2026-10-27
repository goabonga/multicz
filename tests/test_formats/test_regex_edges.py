# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.regex import RegexFormat


def test_regex_write_no_match(tmp_path: Path):
    f = tmp_path / "v.py"
    f.write_text("nothing\n")
    with pytest.raises(FormatError, match="matched nothing"):
        RegexFormat().write(f, "regex:^VERSION = (\\d+)$", "2")
