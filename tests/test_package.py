# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

import importlib
from importlib.metadata import PackageNotFoundError

import pytest

import multicz


def test_version_falls_back_without_installed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", missing)
    try:
        assert importlib.reload(multicz).__version__ == "0.0.0"
    finally:
        monkeypatch.undo()
        importlib.reload(multicz)
