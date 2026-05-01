"""Tests focused on Config parsing semantics, including both supported
syntaxes for declaring components."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from multicz.config import Config, load_config


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
