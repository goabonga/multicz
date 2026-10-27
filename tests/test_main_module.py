# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

import runpy
import sys

import pytest


def test_running_the_package_starts_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["multicz", "--version"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("multicz", run_name="__main__")
    assert stop.value.code == 0
