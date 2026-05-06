# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Tests focused on Config parsing semantics, including both supported
syntaxes for declaring components."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from multicz.config import Config, find_config, load_config


def _write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "multicz.toml"
    target.write_text(body)
    return target


def test_dict_of_tables_form(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["src/**", "pyproject.toml"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [components.chart]
        paths = ["charts/**"]
        bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
        """,
    )
    config = load_config(target)
    assert set(config.components) == {"api", "chart"}


def test_array_of_tables_form(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "api"
        paths = ["src/**", "pyproject.toml"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [[components]]
        name = "chart"
        paths = ["charts/**"]
        bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
        """,
    )
    config = load_config(target)
    assert set(config.components) == {"api", "chart"}
    # name was extracted, not stored on the Component itself
    api = config.components["api"]
    assert api.paths == ["src/**", "pyproject.toml"]
    assert api.bump_files[0].key == "project.version"


def test_array_form_preserves_declaration_order(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "first"
        paths = ["a/**"]

        [[components]]
        name = "second"
        paths = ["b/**"]

        [[components]]
        name = "third"
        paths = ["c/**"]
        """,
    )
    config = load_config(target)
    # ComponentMatcher relies on declaration order for first-match-wins
    assert list(config.components) == ["first", "second", "third"]


def test_array_form_rejects_missing_name(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "name" in str(exc.value)


def test_array_form_rejects_duplicate_name(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "api"
        paths = ["src/**"]

        [[components]]
        name = "api"
        paths = ["other/**"]
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "duplicate" in str(exc.value).lower()


def test_array_form_rejects_non_string_name(tmp_path: Path):
    # not directly expressible in TOML but model can be invoked from python
    with pytest.raises(ValidationError):
        Config.model_validate(
            {"components": [{"name": 42, "paths": ["src/**"]}]}
        )


def test_array_form_empty_list_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        Config.model_validate({"components": []})


def test_array_form_with_depends_on_resolves(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "base"
        paths = ["base/**"]

        [[components]]
        name = "downstream"
        paths = ["downstream/**"]
        depends_on = ["base"]
        """,
    )
    config = load_config(target)
    config.validate_references()  # must not raise
    assert config.components["downstream"].depends_on == ["base"]


def test_dict_and_array_produce_identical_models():
    dict_form = Config.model_validate({
        "components": {
            "api": {"paths": ["src/**"]},
        }
    })
    array_form = Config.model_validate({
        "components": [
            {"name": "api", "paths": ["src/**"]},
        ]
    })
    assert dict_form.model_dump() == array_form.model_dump()


def test_init_output_round_trips_through_array_form(tmp_path: Path):
    """The init/render path emits dict form, but a hand-edited array-form
    config should still survive a render-then-parse round trip via load."""
    target = _write(
        tmp_path,
        """
        [project]
        initial_version = "0.0.0"

        [[components]]
        name = "alpha"
        paths = ["alpha/**"]
        bump_files = [{ file = "alpha/VERSION" }]
        """,
    )
    config = load_config(target)
    assert config.project.initial_version == "0.0.0"
    assert config.components["alpha"].bump_files[0].file.as_posix() == "alpha/VERSION"
    assert config.components["alpha"].bump_files[0].key is None


def test_debian_writer_allows_bump_files(tmp_path: Path):
    """A component can declare a ``debian-changelog`` writer *and*
    ``bump_files`` simultaneously — the writer is then a pure sink while
    the bump_files entry is the version source of truth (Python wheel +
    .deb dual-publish)."""
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["debian/**", "pyproject.toml"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [[components.api.writers]]
        type = "debian-changelog"
        """,
    )
    config = load_config(target)
    api = config.components["api"]
    assert len(api.writers) == 1
    writer = api.writers[0]
    from multicz.config import DebianChangelogWriter
    assert isinstance(writer, DebianChangelogWriter)
    assert str(api.bump_files[0].file) == "pyproject.toml"


def test_debian_writer_accepts_top_level_changelog_for_dual_rendering(
    tmp_path: Path,
):
    """Components with a ``debian-changelog`` writer may declare a
    top-level `changelog` alongside the writer's ``file`` — the markdown
    file becomes a parallel human-readable rendering of every bump,
    while the Debian stanza stays the version source of truth."""
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["debian/**"]
        changelog = "CHANGELOG.md"

        [[components.api.writers]]
        type = "debian-changelog"
        file = "debian/changelog"
        """,
    )
    config = load_config(target)
    api = config.components["api"]
    assert str(api.changelog) == "CHANGELOG.md"
    assert len(api.writers) == 1
    assert str(api.writers[0].file) == "debian/changelog"


def test_debian_writer_with_defaults(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**", "src/**"]

        [[components.mypkg.writers]]
        type = "debian-changelog"
        """,
    )
    config = load_config(target)
    comp = config.components["mypkg"]
    assert len(comp.writers) == 1
    writer = comp.writers[0]
    assert str(writer.file) == "debian/changelog"
    assert writer.distribution == "UNRELEASED"
    assert writer.urgency == "medium"
    assert writer.debian_revision == 1


def test_debian_writer_with_overrides(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**"]

        [[components.mypkg.writers]]
        type = "debian-changelog"
        file = "packaging/changelog"
        distribution = "stable"
        urgency = "high"
        maintainer = "Chris <chris@example.com>"
        debian_revision = 3
        epoch = 2
        """,
    )
    config = load_config(target)
    writer = config.components["mypkg"].writers[0]
    assert str(writer.file) == "packaging/changelog"
    assert writer.distribution == "stable"
    assert writer.urgency == "high"
    assert writer.maintainer == "Chris <chris@example.com>"
    assert writer.debian_revision == 3
    assert writer.epoch == 2


def test_load_from_pyproject_tool_multicz(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\n'
        'name = "myapp"\n'
        'version = "1.0.0"\n'
        '\n'
        '[tool.multicz]\n'
        '[tool.multicz.components.api]\n'
        'paths = ["src/**", "pyproject.toml"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    config = load_config(pyproject)
    assert "api" in config.components
    assert config.components["api"].paths == ["src/**", "pyproject.toml"]


def test_load_from_pyproject_with_array_of_tables(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\n'
        'name = "myapp"\n'
        'version = "1.0.0"\n'
        '\n'
        '[tool.multicz]\n'
        '\n'
        '[[tool.multicz.components]]\n'
        'name = "api"\n'
        'paths = ["src/**"]\n'
        '\n'
        '[[tool.multicz.components]]\n'
        'name = "web"\n'
        'paths = ["frontend/**"]\n'
    )
    config = load_config(pyproject)
    assert list(config.components) == ["api", "web"]


def test_load_from_package_json(tmp_path: Path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "monorepo",
        "version": "1.0.0",
        "multicz": {
            "components": {
                "web": {
                    "paths": ["src/**", "package.json"],
                    "bump_files": [{"file": "package.json", "key": "version"}],
                }
            }
        }
    }, indent=2))
    config = load_config(pkg)
    assert "web" in config.components


def test_load_from_package_json_with_array_form(tmp_path: Path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "monorepo",
        "multicz": {
            "components": [
                {"name": "web", "paths": ["frontend/**"]},
                {"name": "mobile", "paths": ["mobile/**"]},
            ]
        }
    }))
    config = load_config(pkg)
    assert list(config.components) == ["web", "mobile"]


def test_pyproject_without_tool_multicz_is_skipped(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    with pytest.raises(FileNotFoundError):
        find_config(tmp_path)


def test_package_json_without_multicz_key_is_skipped(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0"}')
    with pytest.raises(FileNotFoundError):
        find_config(tmp_path)


def test_find_config_prefers_multicz_toml(tmp_path: Path):
    """When both files exist, the dedicated multicz.toml wins."""
    _write(tmp_path, '[components.fromdedicated]\npaths = ["src/**"]')
    (tmp_path / "pyproject.toml").write_text(
        '[tool.multicz.components.frompyproject]\npaths = ["src/**"]\n'
    )
    found = find_config(tmp_path)
    assert found.name == "multicz.toml"
    config = load_config(found)
    assert "fromdedicated" in config.components


def test_find_config_prefers_pyproject_over_package_json(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.multicz.components.frompy]\npaths = ["src/**"]\n'
    )
    (tmp_path / "package.json").write_text(
        '{"multicz": {"components": {"fromjs": {"paths": ["src/**"]}}}}'
    )
    found = find_config(tmp_path)
    assert found.name == "pyproject.toml"


def test_find_config_walks_up(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.multicz.components.api]\npaths = ["src/**"]\n'
    )
    nested = tmp_path / "deep" / "nested" / "dir"
    nested.mkdir(parents=True)
    found = find_config(nested)
    assert found == pyproject


def test_find_config_raises_with_helpful_message(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as exc:
        find_config(tmp_path)
    assert "multicz.toml" in str(exc.value)
    assert "pyproject.toml" in str(exc.value)
    assert "package.json" in str(exc.value)


def test_component_name_with_slash_is_rejected(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components."api/v1"]
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    msg = str(exc.value)
    assert "invalid component name" in msg
    assert "'api/v1'" in msg


def test_component_name_with_path_traversal_is_rejected(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components."../api"]
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_component_name_with_colon_is_rejected(tmp_path: Path):
    """Colon would conflict with --force NAME:KIND CLI syntax."""
    target = _write(
        tmp_path,
        """
        [components."chart:prod"]
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_component_name_with_space_is_rejected(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components."my app"]
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_component_name_leading_or_trailing_special_is_rejected(tmp_path: Path):
    for bad in ("-foo", "foo-", ".hidden", "foo."):
        target = _write(
            tmp_path,
            f'[components."{bad}"]\npaths = ["src/**"]\n',
        )
        with pytest.raises(ValidationError):
            load_config(target)


def test_component_name_too_long_is_rejected(tmp_path: Path):
    long_name = "a" * 65
    target = _write(
        tmp_path,
        f'[components.{long_name}]\npaths = ["src/**"]\n',
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "too long" in str(exc.value)


def test_valid_component_names(tmp_path: Path):
    """The accepted forms - all common naming conventions.

    Dots in TOML keys need quoting (otherwise the parser reads them as
    nested tables), but the *resolved* component name still passes.
    """
    cases = [
        ("a", '[components.a]'),
        ("api", '[components.api]'),
        ("api-v1", '[components.api-v1]'),
        ("api.v1", '[components."api.v1"]'),
        ("api_v1", '[components.api_v1]'),
        ("myapp-chart", '[components.myapp-chart]'),
        ("API", '[components.API]'),
    ]
    for resolved_name, header in cases:
        target = _write(tmp_path, f'{header}\npaths = ["src/**"]\n')
        config = load_config(target)
        assert resolved_name in config.components


def test_array_form_name_is_validated(tmp_path: Path):
    """The same rules apply to the array-of-tables 'name = ...' field."""
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "api/v1"
        paths = ["src/**"]
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_per_component_tag_format_override(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [project]
        tag_format = "{component}-v{version}"

        [components.api]
        paths = ["src/**"]

        [components.legacy]
        paths = ["legacy/**"]
        tag_format = "v{version}"
        """,
    )
    config = load_config(target)
    assert config.tag_format_for("api") == "{component}-v{version}"
    assert config.tag_format_for("legacy") == "v{version}"


def test_unique_prefix_per_component_is_required(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [project]
        tag_format = "v{version}"

        [components.foo]
        paths = ["a/**"]

        [components.bar]
        paths = ["b/**"]
        """,
    )
    with pytest.raises(ValueError) as exc:
        load_config(target)
    assert "tag prefix" in str(exc.value)
    assert "collide" in str(exc.value)


def test_collision_resolved_by_per_component_override(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [project]
        tag_format = "v{version}"

        [components.legacy]
        paths = ["legacy/**"]

        [components.api]
        paths = ["src/**"]
        tag_format = "api-v{version}"
        """,
    )
    config = load_config(target)
    config.validate_references()  # must not raise
    assert config._render_tag_prefix("legacy") == "v"
    assert config._render_tag_prefix("api") == "api-v"


def test_static_tag_format_without_component_placeholder(tmp_path: Path):
    """A literal format like 'release-{version}' works as long as it's
    unique across components (here only one uses it)."""
    target = _write(
        tmp_path,
        """
        [components.thing]
        paths = ["src/**"]
        tag_format = "release-{version}"
        """,
    )
    config = load_config(target)
    config.validate_references()
    assert config._render_tag_prefix("thing") == "release-"


def test_pep440_scheme_with_debian_writer_is_rejected(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**"]
        version_scheme = "pep440"

        [[components.mypkg.writers]]
        type = "debian-changelog"
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "version_scheme='semver'" in str(exc.value)


def test_load_config_rejects_components_array_with_extra_fields(tmp_path: Path):
    """Component still has extra='forbid', so unknown fields fail even in array form."""
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "api"
        paths = ["src/**"]
        wat = "no"
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_mirror_accepts_changelog_section_and_format(tmp_path: Path):
    """Mirror gains optional changelog_section and changelog_format fields
    used to customize how the cascade line shows up in the downstream
    component's CHANGELOG.md."""
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["src/**"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [[components.api.mirrors]]
        file = "charts/myapp/Chart.yaml"
        key = "appVersion"
        changelog_section = "Features"
        changelog_format = "Sync app to {upstream_version}"
        """,
    )
    config = load_config(target)
    mirror = config.components["api"].mirrors[0]
    assert mirror.changelog_section == "Features"
    assert mirror.changelog_format == "Sync app to {upstream_version}"


def test_mirror_changelog_fields_default_to_none(tmp_path: Path):
    """When the new fields are omitted, the mirror falls back to the
    project-level cascade_title / cascade_format."""
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["src/**"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]
        mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
        """,
    )
    config = load_config(target)
    mirror = config.components["api"].mirrors[0]
    assert mirror.changelog_section is None
    assert mirror.changelog_format is None


def test_mirror_rejects_unknown_field(tmp_path: Path):
    """Mirror still has extra='forbid' (inherited from FileKey)."""
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["src/**"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [[components.api.mirrors]]
        file = "charts/myapp/Chart.yaml"
        key = "appVersion"
        wat = "no"
        """,
    )
    with pytest.raises(ValidationError):
        load_config(target)


# ---------------------------------------------------------------------------
# bump_rules
# ---------------------------------------------------------------------------


def _minimal_component(extra: str = "") -> str:
    """Single-component config used by the bump_rules tests."""
    return f"""
[components.api]
paths = ["src/**"]
bump_files = [{{ file = "pyproject.toml", key = "project.version" }}]
{extra}
"""


def test_bump_rules_default_matches_default_bump_rules(tmp_path: Path):
    """Without an explicit `[project.bump_rules]` table, the project
    inherits :data:`DEFAULT_BUMP_RULES`."""
    from multicz.commits import DEFAULT_BUMP_RULES

    target = _write(tmp_path, _minimal_component())
    config = load_config(target)
    assert config.project.bump_rules == DEFAULT_BUMP_RULES


def test_bump_rules_user_entries_merge_on_top_of_defaults(tmp_path: Path):
    """User entries merge on top of :data:`DEFAULT_BUMP_RULES`. Adding
    ``infra = "patch"`` keeps the conventional ``feat`` / ``fix`` / ``perf``
    / ``revert`` defaults — no footgun on sparse user tables."""
    target = _write(
        tmp_path,
        """
[project.bump_rules]
infra = "patch"
"""
        + _minimal_component(),
    )
    config = load_config(target)
    rules = config.project.bump_rules
    assert rules == {
        "feat": "minor",
        "fix": "patch",
        "perf": "patch",
        "revert": "patch",
        "infra": "patch",
    }


def test_bump_rules_user_can_silence_default(tmp_path: Path):
    """``feat = "none"`` overrides the default ``feat = "minor"``."""
    target = _write(
        tmp_path,
        """
[project.bump_rules]
feat = "none"
"""
        + _minimal_component(),
    )
    config = load_config(target)
    assert config.project.bump_rules["feat"] == "none"


def test_bump_rules_keys_are_lowercased(tmp_path: Path):
    target = _write(
        tmp_path,
        """
[project.bump_rules]
FEAT = "minor"
"""
        + _minimal_component(),
    )
    config = load_config(target)
    assert "feat" in config.project.bump_rules
    assert "FEAT" not in config.project.bump_rules


def test_bump_rules_rejects_invalid_value(tmp_path: Path):
    target = _write(
        tmp_path,
        """
[project.bump_rules]
feat = "wibble"
"""
        + _minimal_component(),
    )
    with pytest.raises(ValidationError):
        load_config(target)


def test_bump_rules_for_merges_project_and_component(tmp_path: Path):
    target = _write(
        tmp_path,
        """
[project.bump_rules]
feat = "minor"
fix = "patch"
"""
        + _minimal_component('bump_rules = { feat = "patch" }'),
    )
    config = load_config(target)
    rules = config.bump_rules_for("api")
    # Component override wins per-type; project entries pass through.
    assert rules["feat"] == "patch"
    assert rules["fix"] == "patch"


def test_legacy_ignored_types_field_is_rejected(tmp_path: Path):
    """``ignored_types`` was removed in v1; the schema now rejects it."""
    target = _write(
        tmp_path,
        """
[project]
ignored_types = ["chore"]
"""
        + _minimal_component(),
    )
    with pytest.raises(ValidationError, match="ignored_types"):
        load_config(target)


def test_legacy_triggers_field_is_rejected(tmp_path: Path):
    """``triggers`` was a parse-time alias for ``depends_on`` and is
    removed in v1; the schema now rejects it."""
    target = _write(
        tmp_path,
        """
[components.api]
paths = ["src/**"]

[components.chart]
paths = ["charts/**"]
triggers = ["api"]
""",
    )
    with pytest.raises(ValidationError, match="triggers"):
        load_config(target)
