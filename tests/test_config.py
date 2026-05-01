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


def test_array_form_with_triggers_resolves(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [[components]]
        name = "base"
        paths = ["base/**"]

        [[components]]
        name = "downstream"
        paths = ["downstream/**"]
        triggers = ["base"]
        """,
    )
    config = load_config(target)
    config.validate_references()  # must not raise
    assert config.components["downstream"].triggers == ["base"]


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


def test_debian_format_requires_no_bump_files(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["debian/**"]
        format = "debian"
        bump_files = [{ file = "debian/changelog" }]
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "bump_files" in str(exc.value)


def test_debian_format_rejects_top_level_changelog(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["debian/**"]
        format = "debian"
        changelog = "CHANGELOG.md"
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "components.<name>.debian" in str(exc.value)


def test_debian_settings_only_with_debian_format(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.api]
        paths = ["src/**"]
        bump_files = [{ file = "pyproject.toml", key = "project.version" }]

        [components.api.debian]
        changelog = "debian/changelog"
        """,
    )
    with pytest.raises(ValidationError) as exc:
        load_config(target)
    assert "format = 'debian'" in str(exc.value)


def test_debian_format_with_defaults(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**", "src/**"]
        format = "debian"
        """,
    )
    config = load_config(target)
    comp = config.components["mypkg"]
    assert comp.format == "debian"
    assert comp.debian is not None  # auto-filled
    assert str(comp.debian.changelog) == "debian/changelog"
    assert comp.debian.distribution == "UNRELEASED"
    assert comp.debian.urgency == "medium"
    assert comp.debian.debian_revision == 1


def test_debian_format_with_overrides(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**"]
        format = "debian"

        [components.mypkg.debian]
        changelog = "packaging/changelog"
        distribution = "stable"
        urgency = "high"
        maintainer = "Chris <chris@example.com>"
        debian_revision = 3
        epoch = 2
        """,
    )
    config = load_config(target)
    settings = config.components["mypkg"].debian
    assert str(settings.changelog) == "packaging/changelog"
    assert settings.distribution == "stable"
    assert settings.urgency == "high"
    assert settings.maintainer == "Chris <chris@example.com>"
    assert settings.debian_revision == 3
    assert settings.epoch == 2


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


def test_pep440_scheme_with_debian_format_is_rejected(tmp_path: Path):
    target = _write(
        tmp_path,
        """
        [components.mypkg]
        paths = ["debian/**"]
        format = "debian"
        version_scheme = "pep440"
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
