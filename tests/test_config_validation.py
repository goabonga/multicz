# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Config model validators rejecting malformed input."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from multicz.config import Config


def _component(**fields) -> dict:
    return {"components": {"api": {"paths": ["src/**"], **fields}}}


def test_post_bump_with_unbalanced_quote_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a valid shell command"):
        Config.model_validate(_component(post_bump=['echo "unterminated']))


def test_duplicate_writer_file_is_rejected() -> None:
    writer = {"type": "debian-changelog", "file": "debian/changelog"}
    with pytest.raises(ValidationError, match="duplicate writer file"):
        Config.model_validate(_component(writers=[writer, writer]))


def test_non_table_project_bump_rules_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({**_component(), "project": {"bump_rules": "minor"}})


def test_non_table_config_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(["not", "a", "table"])
