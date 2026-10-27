# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Component files merged into the root config through ``[[component.path]]``."""

from pathlib import Path

import pytest

from multicz.config import COMPONENT_FILENAME, ComponentMatcher, find_config, load_config
from multicz.config.includes import find_component_files


def _paths(*patterns: str) -> str:
    return "".join(f'[[component.path]]\npath = "{p}"\n' for p in patterns)


def _root(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "multicz.toml"
    target.write_text(body)
    return target


def _component(tmp_path: Path, directory: str, body: str) -> Path:
    target = tmp_path / directory / COMPONENT_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    return target


def test_no_component_path_leaves_the_config_alone(tmp_path: Path):
    root = _root(tmp_path, '[components.api]\npaths = ["src/**"]\n')
    config = load_config(root)
    assert set(config.components) == {"api"}
    assert config.source_files == [root]


def test_directory_pattern_selects_its_component_file(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/app"))
    _component(tmp_path, "packages/app", "[components.app]\n")
    assert set(load_config(root).components) == {"app"}


def test_wildcard_pattern_selects_every_directory(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    _component(tmp_path, "packages/b", "[components.b]\n")
    (tmp_path / "packages/empty").mkdir()
    (tmp_path / "packages/README.md").write_text("not a component")
    config = load_config(root)
    assert list(config.components) == ["a", "b"]
    assert config.source_files == [
        root,
        tmp_path / "packages/a" / COMPONENT_FILENAME,
        tmp_path / "packages/b" / COMPONENT_FILENAME,
    ]


def test_recursive_pattern_reaches_nested_directories(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/**/*"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    _component(tmp_path, "packages/group/b", "[components.b]\n")
    assert set(load_config(root).components) == {"a", "b"}


def test_a_file_matched_twice_is_read_once(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*", "packages/a", "packages/*/*.toml"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert load_config(root).source_files.count(tmp_path / "packages/a" / COMPONENT_FILENAME) == 1


def test_dot_directories_are_not_walked(tmp_path: Path):
    root = _root(tmp_path, _paths("**/*"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    _component(tmp_path, ".venv/lib/stray", "[components.stray]\n")
    assert set(load_config(root).components) == {"a"}


def test_root_and_merged_components_coexist(tmp_path: Path):
    root = _root(
        tmp_path,
        _paths("packages/*") + '[components.core]\npaths = ["core/**"]\n',
    )
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert list(load_config(root).components) == ["core", "a"]


def test_root_components_may_use_the_array_form(tmp_path: Path):
    root = _root(
        tmp_path,
        _paths("packages/*") + '[[components]]\nname = "core"\npaths = ["core/**"]\n',
    )
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert list(load_config(root).components) == ["core", "a"]


def test_component_file_may_use_the_array_form(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", '[[components]]\nname = "a"\n')
    assert set(load_config(root).components) == {"a"}


def test_component_paths_work_from_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[[tool.multicz.component.path]]\npath = "packages/*"\n'
    )
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert set(load_config(tmp_path / "pyproject.toml").components) == {"a"}


def test_paths_default_to_the_whole_directory(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert load_config(root).components["a"].paths == ["packages/a/**"]


def test_component_file_at_the_root_directory_is_not_rebased(tmp_path: Path):
    root = _root(tmp_path, _paths("multicz.component.toml"))
    _component(tmp_path, ".", '[components.a]\npaths = ["src/**"]\nchangelog = "CHANGELOG.md"\n')
    component = load_config(root).components["a"]
    assert component.paths == ["src/**"]
    assert component.changelog == Path("CHANGELOG.md")


@pytest.mark.parametrize(
    ("declared", "rebased"),
    [
        ("src/**", "packages/a/src/**"),
        ("/src", "packages/a/src"),
        ("./src/**", "packages/a/src/**"),
        ("*.py", "packages/a/**/*.py"),
        ("**", "packages/a/**"),
        ("!src/gen/**", "!packages/a/src/gen/**"),
        ("!*.pyc", "!packages/a/**/*.pyc"),
        ("docs/", "packages/a/**/docs/"),
        ("src/docs/", "packages/a/src/docs/"),
    ],
)
def test_globs_keep_their_gitignore_meaning(tmp_path: Path, declared: str, rebased: str):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", f'[components.a]\npaths = ["{declared}"]\n')
    assert load_config(root).components["a"].paths == [rebased]


def test_unanchored_pattern_still_matches_at_depth(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", '[components.a]\npaths = ["*.py"]\n')
    matcher = ComponentMatcher(load_config(root).components)
    assert matcher.match("packages/a/deep/er/mod.py") == "a"
    assert matcher.match("packages/b/mod.py") is None


def test_exclude_paths_are_rebased_too(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", '[components.a]\nexclude_paths = ["tests/**"]\n')
    matcher = ComponentMatcher(load_config(root).components)
    assert matcher.match("packages/a/src/x.py") == "a"
    assert matcher.match("packages/a/tests/x.py") is None


def test_file_fields_are_rebased(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(
        tmp_path,
        "packages/a",
        """
        [components.a]
        changelog = "CHANGELOG.md"
        bump_files = [{ file = "PKGBUILD", key = "pkgver" }]
        mirrors = [{ file = "../shared/VERSION" }]

        [[components.a.writers]]
        type = "debian-changelog"
        """,
    )
    component = load_config(root).components["a"]
    assert component.changelog == Path("packages/a/CHANGELOG.md")
    assert component.bump_files[0].file == Path("packages/a/PKGBUILD")
    assert component.mirrors[0].file == Path("packages/shared/VERSION")
    assert component.writers[0].file == Path("packages/a/debian/changelog")


def test_post_bump_is_left_as_written(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a") + '[project]\npost_bump_policy = "allow"\n')
    _component(tmp_path, "packages/a", '[components.a]\npost_bump = ["make lock"]\n')
    assert load_config(root).components["a"].post_bump == ["make lock"]


def test_depends_on_crosses_files(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*"))
    _component(tmp_path, "packages/lib", "[components.lib]\n")
    _component(tmp_path, "packages/app", '[components.app]\ndepends_on = ["lib"]\n')
    assert load_config(root).components["app"].depends_on == ["lib"]


def test_unknown_dependency_is_still_rejected(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/app"))
    _component(tmp_path, "packages/app", '[components.app]\ndepends_on = ["ghost"]\n')
    with pytest.raises(ValueError, match="ghost"):
        load_config(root)


def test_duplicate_name_across_files_names_both(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*"))
    _component(tmp_path, "packages/a", "[components.dup]\n")
    _component(tmp_path, "packages/b", "[components.dup]\n")
    with pytest.raises(ValueError, match=r"packages/a/.*packages/b/"):
        load_config(root)


def test_duplicate_name_with_the_root_is_rejected(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a") + '[components.a]\npaths = ["x/**"]\n')
    _component(tmp_path, "packages/a", "[components.a]\n")
    with pytest.raises(ValueError, match="root config"):
        load_config(root)


def test_a_literal_pattern_must_exist(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/missing") + '[components.a]\npaths = ["a/**"]\n')
    with pytest.raises(ValueError, match="packages/missing"):
        load_config(root)


def test_a_wildcard_matching_nothing_is_fine(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*") + '[components.a]\npaths = ["a/**"]\n')
    assert set(load_config(root).components) == {"a"}


@pytest.mark.parametrize("pattern", ["../outside", "/etc", "packages/../../x", ""])
def test_patterns_must_stay_inside_the_repository(tmp_path: Path, pattern: str):
    root = _root(tmp_path, _paths(pattern) + '[components.a]\npaths = ["a/**"]\n')
    with pytest.raises(ValueError, match="inside the repository"):
        load_config(root)


def test_each_entry_needs_a_string_path(tmp_path: Path):
    root = _root(tmp_path, "[[component.path]]\npath = 1\n" + '[components.a]\npaths = ["a/**"]\n')
    with pytest.raises(ValueError, match=r"component -> path -> 0 -> path"):
        load_config(root)


def test_an_entry_without_a_path_is_rejected(tmp_path: Path):
    root = _root(tmp_path, "[[component.path]]\n" + '[components.a]\npaths = ["a/**"]\n')
    with pytest.raises(ValueError, match="path"):
        load_config(root)


def test_unknown_entry_options_are_rejected(tmp_path: Path):
    root = _root(
        tmp_path,
        '[[component.path]]\npath = "packages/a"\nbogus = 1\n',
    )
    with pytest.raises(ValueError, match="bogus"):
        load_config(root)


def test_several_entries_are_merged_in_declaration_order(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*", "apps/*"))
    _component(tmp_path, "packages/p", "[components.p]\n")
    _component(tmp_path, "apps/a", "[components.a]\n")
    config = load_config(root)
    assert set(config.components) == {"p", "a"}
    assert [e.path for e in config.component.path] == ["packages/*", "apps/*"]


def test_component_file_cannot_carry_project_settings(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", '[project]\ntag_format = "x"\n[components.a]\n')
    with pytest.raises(ValueError, match=r"only \[components\].*project"):
        load_config(root)


def test_component_file_cannot_declare_further_paths(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", _paths("x") + "[components.a]\n")
    with pytest.raises(ValueError, match=r"found: component"):
        load_config(root)


def test_empty_component_file_is_rejected(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", "")
    with pytest.raises(ValueError, match="declares no component"):
        load_config(root)


def test_malformed_component_file_names_the_file(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", "[components.a\n")
    with pytest.raises(ValueError, match=r"packages/a/.*TOML"):
        load_config(root)


def test_invalid_component_names_the_file(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", "[components.a]\nbogus = 1\n")
    with pytest.raises(ValueError, match=r"packages/a/.*component 'a'.*bogus"):
        load_config(root)


@pytest.mark.parametrize(
    "line",
    ['paths = ["../x/**"]', 'exclude_paths = ["../x"]', 'changelog = "../../../CHANGELOG.md"'],
)
def test_paths_cannot_escape_the_repository(tmp_path: Path, line: str):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", f"[components.a]\n{line}\n")
    with pytest.raises(ValueError, match="inside"):
        load_config(root)


def test_find_config_is_not_fooled_by_a_component_file(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    assert find_config(tmp_path / "packages/a") == root


def test_files_are_ordered_by_path(tmp_path: Path):
    _component(tmp_path, "packages/b", "[components.b]\n")
    _component(tmp_path, "packages/a", "[components.a]\n")
    files = find_component_files(["packages/*"], tmp_path)
    assert [f.parent.name for f in files] == ["a", "b"]


def test_a_component_table_without_paths_merges_nothing(tmp_path: Path):
    root = _root(tmp_path, '[component]\n[components.a]\npaths = ["a/**"]\n')
    config = load_config(root)
    assert set(config.components) == {"a"}
    assert config.source_files == [root]


def test_root_components_array_entries_must_be_tables(tmp_path: Path):
    root = _root(tmp_path, 'components = ["a"]\n')
    with pytest.raises(ValueError, match="must be a table"):
        load_config(root)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('bump_files = ["version.json"]', "bump_files"),
        ('bump_files = [{ key = "version" }]', "bump_files"),
        ('writers = ["debian"]', "writers"),
    ],
)
def test_malformed_file_entries_are_reported_with_their_file(
    tmp_path: Path, body: str, message: str
):
    root = _root(tmp_path, _paths("packages/a"))
    _component(tmp_path, "packages/a", f"[components.a]\n{body}\n")
    with pytest.raises(ValueError, match=rf"packages/a/.*{message}"):
        load_config(root)


def test_the_dump_has_no_component_table_when_none_is_declared(tmp_path: Path):
    root = _root(tmp_path, '[components.a]\npaths = ["a/**"]\n')
    assert "component" not in load_config(root).model_dump(mode="json")


def test_the_dump_keeps_the_declared_component_paths(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*"))
    _component(tmp_path, "packages/a", "[components.a]\n")
    dumped = load_config(root).model_dump(mode="json")
    assert dumped["component"] == {"path": [{"path": "packages/*"}]}


def test_root_component_can_depend_on_a_merged_one(tmp_path: Path):
    root = _root(
        tmp_path,
        _paths("packages/*") + '[components.core]\npaths = ["core/**"]\ndepends_on = ["lib"]\n',
    )
    _component(tmp_path, "packages/lib", "[components.lib]\n")
    assert load_config(root).components["core"].depends_on == ["lib"]


def test_merged_component_can_depend_on_a_root_one(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*") + '[components.core]\npaths = ["core/**"]\n')
    _component(tmp_path, "packages/app", '[components.app]\ndepends_on = ["core"]\n')
    assert load_config(root).components["app"].depends_on == ["core"]


def test_merged_components_can_depend_on_each_other_across_entries(tmp_path: Path):
    root = _root(tmp_path, _paths("packages/*", "apps/*"))
    _component(tmp_path, "packages/lib", "[components.lib]\n")
    _component(tmp_path, "apps/app", '[components.app]\ndepends_on = ["lib"]\n')
    assert load_config(root).components["app"].depends_on == ["lib"]


def test_root_component_depending_on_an_unknown_name_is_rejected(tmp_path: Path):
    root = _root(
        tmp_path,
        _paths("packages/*") + '[components.core]\npaths = ["core/**"]\ndepends_on = ["ghost"]\n',
    )
    _component(tmp_path, "packages/lib", "[components.lib]\n")
    with pytest.raises(ValueError, match="ghost"):
        load_config(root)
