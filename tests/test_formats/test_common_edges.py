# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

import pytest

from multicz.formats import FormatError
from multicz.formats._common import navigate, split_key


def test_split_key_rejects_empty():
    with pytest.raises(FormatError, match="empty key"):
        split_key("..")


def test_navigate_missing_segment_without_create():
    with pytest.raises(FormatError, match="missing key 'a'"):
        navigate({}, ["a", "b"], create=False)
