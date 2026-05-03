# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Optional persistent state file written after each successful bump.

Multicz is normally stateless — every command recomputes from git tags
and the in-tree manifests. For monorepos that benefit from a recorded
"last release" snapshot (audit trail, drift detection between manual
edits and the planner's view, faster CI gates), opt into a state file
via ``[project].state_file = ".multicz/state.json"``.

The format is JSON for easy ``jq`` consumption::

    {
      "version": 1,
      "git_head": "abc1234567890abcdef…",
      "git_head_short": "abc1234",
      "timestamp": "2026-05-01T10:00:00Z",
      "components": {
        "api": {
          "version": "1.3.0",
          "tag": "api-v1.3.0",
          "tag_sha": "def5678…"
        },
        "chart": {
          "version": "0.4.1",
          "tag": "chart-v0.4.1",
          "tag_sha": "ghi9012…"
        }
      }
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

STATE_SCHEMA_VERSION = 1


@dataclass
class ComponentState:
    version: str
    tag: str | None = None
    tag_sha: str | None = None


@dataclass
class State:
    version: int
    git_head: str
    git_head_short: str
    timestamp: str
    components: dict[str, ComponentState] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "git_head": self.git_head,
            "git_head_short": self.git_head_short,
            "timestamp": self.timestamp,
            "components": {n: asdict(c) for n, c in self.components.items()},
        }


def now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Path) -> State | None:
    """Read a state file, or return ``None`` if it doesn't exist."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    components = {
        name: ComponentState(
            version=str(c.get("version", "")),
            tag=c.get("tag"),
            tag_sha=c.get("tag_sha"),
        )
        for name, c in (data.get("components") or {}).items()
        if isinstance(c, dict)
    }
    return State(
        version=int(data.get("version", 0) or 0),
        git_head=str(data.get("git_head", "") or ""),
        git_head_short=str(data.get("git_head_short", "") or ""),
        timestamp=str(data.get("timestamp", "") or ""),
        components=components,
    )


def write_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
