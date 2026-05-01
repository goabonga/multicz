from pathlib import Path

from multicz.config import Config
from multicz.discovery import discover_components, render_config


def _python_project(repo: Path, name: str = "myapp") -> None:
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.0.0"\n'
    )
    (repo / "src").mkdir()


def _chart(repo: Path, dirname: str, chart_name: str | None = None) -> None:
    chart_dir = repo / "charts" / dirname
    chart_dir.mkdir(parents=True)
    yaml_name = chart_name or dirname
    (chart_dir / "Chart.yaml").write_text(
        f"apiVersion: v2\nname: {yaml_name}\nversion: 0.1.0\nappVersion: 1.0.0\n"
    )


def test_python_only(tmp_path: Path):
    _python_project(tmp_path)
    comps = discover_components(tmp_path)
    assert list(comps) == ["myapp"]
    paths = comps["myapp"].paths
    assert "src/**" in paths
    assert "pyproject.toml" in paths
    assert "Dockerfile" not in paths
    assert ".dockerignore" not in paths
    assert comps["myapp"].mirrors == []


def test_dockerfile_added_when_present(tmp_path: Path):
    _python_project(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    comps = discover_components(tmp_path)
    assert "Dockerfile" in comps["myapp"].paths


def test_dockerignore_is_never_auto_added(tmp_path: Path):
    """`.dockerignore` is build-context hygiene, not an artifact change.

    Including it would silently bump the api on routine cleanup.
    Users who want it can add it manually.
    """
    _python_project(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    (tmp_path / ".dockerignore").write_text("__pycache__\n")
    comps = discover_components(tmp_path)
    assert ".dockerignore" not in comps["myapp"].paths


def test_tests_dir_only_added_when_present(tmp_path: Path):
    _python_project(tmp_path)
    comps = discover_components(tmp_path)
    assert "tests/**" not in comps["myapp"].paths

    (tmp_path / "tests").mkdir()
    comps = discover_components(tmp_path)
    assert "tests/**" in comps["myapp"].paths


def test_chart_alongside_python_wires_app_version_mirror(tmp_path: Path):
    _python_project(tmp_path, name="myapp")
    _chart(tmp_path, dirname="myapp-chart")
    comps = discover_components(tmp_path)

    assert "myapp" in comps
    assert "myapp-chart" in comps
    mirrors = comps["myapp"].mirrors
    assert len(mirrors) == 1
    assert mirrors[0].key == "appVersion"
    assert "Chart.yaml" in str(mirrors[0].file)


def test_chart_only_no_mirror(tmp_path: Path):
    _chart(tmp_path, dirname="thing")
    comps = discover_components(tmp_path)
    assert list(comps) == ["thing"]
    assert comps["thing"].mirrors == []
    assert comps["thing"].paths == ["charts/thing/**"]


def test_chart_collision_suffixes(tmp_path: Path):
    _python_project(tmp_path, name="myapp")
    _chart(tmp_path, dirname="myapp")  # same name as the python project
    comps = discover_components(tmp_path)

    assert "myapp" in comps
    assert "myapp-chart" in comps
    assert comps["myapp-chart"].paths == ["charts/myapp/**"]


def test_multiple_charts_independent(tmp_path: Path):
    _chart(tmp_path, dirname="api")
    _chart(tmp_path, dirname="worker")
    _chart(tmp_path, dirname="cron")

    comps = discover_components(tmp_path)
    assert {"api", "worker", "cron"}.issubset(comps)
    for name in ("api", "worker", "cron"):
        assert comps[name].mirrors == []
        assert comps[name].paths == [f"charts/{name}/**"]


def test_multiple_charts_with_python_only_mirrors_matching_name(tmp_path: Path):
    _python_project(tmp_path, name="api")
    _chart(tmp_path, dirname="api")        # chart name matches -> mirror
    _chart(tmp_path, dirname="worker")     # different name -> no mirror

    comps = discover_components(tmp_path)
    api_mirrors = comps["api"].mirrors
    assert len(api_mirrors) == 1
    assert "charts/api/Chart.yaml" in str(api_mirrors[0].file)


def test_single_python_single_chart_mirrors_even_with_different_names(tmp_path: Path):
    _python_project(tmp_path, name="myapp")
    _chart(tmp_path, dirname="deployment")  # different name, but only one chart

    comps = discover_components(tmp_path)
    mirrors = comps["myapp"].mirrors
    assert len(mirrors) == 1
    assert "charts/deployment/Chart.yaml" in str(mirrors[0].file)


def test_chart_under_helm_dir(tmp_path: Path):
    helm_dir = tmp_path / "helm" / "myapp"
    helm_dir.mkdir(parents=True)
    (helm_dir / "Chart.yaml").write_text(
        "apiVersion: v2\nname: myapp\nversion: 0.1.0\n"
    )
    comps = discover_components(tmp_path)
    assert "myapp" in comps
    assert comps["myapp"].paths == ["helm/myapp/**"]


def test_chart_under_deploy_dir(tmp_path: Path):
    deploy = tmp_path / "deploy" / "k8s" / "service-a"
    deploy.mkdir(parents=True)
    (deploy / "Chart.yaml").write_text(
        "apiVersion: v2\nname: service-a\nversion: 0.1.0\n"
    )
    comps = discover_components(tmp_path)
    assert "service-a" in comps


def test_chart_in_node_modules_is_skipped(tmp_path: Path):
    _python_project(tmp_path)
    nm = tmp_path / "node_modules" / "some-pkg" / "Chart.yaml"
    nm.parent.mkdir(parents=True)
    nm.write_text("apiVersion: v2\nname: leaked\nversion: 0.1.0\n")

    comps = discover_components(tmp_path)
    assert "leaked" not in comps


def test_cargo_plain_crate_at_root(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "myapp"\nversion = "0.1.0"\n'
    )
    (tmp_path / "src").mkdir()
    comps = discover_components(tmp_path)
    assert "myapp" in comps
    bf = comps["myapp"].bump_files[0]
    assert bf.key == "package.version"
    assert str(bf.file) == "Cargo.toml"
    assert "src/**" in comps["myapp"].paths


def test_cargo_workspace_with_shared_version(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/foo", "crates/bar"]\n'
        '\n[workspace.package]\nversion = "0.1.0"\n'
    )
    foo = tmp_path / "crates" / "foo"
    foo.mkdir(parents=True)
    (foo / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion.workspace = true\n'
    )
    bar = tmp_path / "crates" / "bar"
    bar.mkdir(parents=True)
    (bar / "Cargo.toml").write_text(
        '[package]\nname = "bar"\nversion.workspace = true\n'
    )

    comps = discover_components(tmp_path)
    # only the root workspace component is added; members inherit
    assert "foo" not in comps
    assert "bar" not in comps
    # the root crate has no [package].name in this layout, so no component for the workspace
    # (a "virtual workspace") -> nothing is added. That's the correct behavior.


def test_cargo_workspace_with_shared_version_and_root_package(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "rootkit"\nversion = "0.1.0"\n'
        '\n[workspace]\nmembers = ["crates/foo"]\n'
        '\n[workspace.package]\nversion = "0.1.0"\n'
    )
    foo = tmp_path / "crates" / "foo"
    foo.mkdir(parents=True)
    (foo / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion.workspace = true\n'
    )
    comps = discover_components(tmp_path)
    assert "rootkit" in comps
    assert comps["rootkit"].bump_files[0].key == "workspace.package.version"
    assert "foo" not in comps  # member inherits


def test_cargo_independent_member_crates(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/foo", "crates/bar"]\n'
    )
    foo = tmp_path / "crates" / "foo"
    foo.mkdir(parents=True)
    (foo / "Cargo.toml").write_text(
        '[package]\nname = "foo"\nversion = "1.0.0"\n'
    )
    bar = tmp_path / "crates" / "bar"
    bar.mkdir(parents=True)
    (bar / "Cargo.toml").write_text(
        '[package]\nname = "bar"\nversion = "2.0.0"\n'
    )
    comps = discover_components(tmp_path)
    assert {"foo", "bar"}.issubset(comps)
    assert comps["foo"].paths == ["crates/foo/**"]
    assert comps["bar"].paths == ["crates/bar/**"]


def test_cargo_in_target_dir_skipped(tmp_path: Path):
    target_cargo = tmp_path / "target" / "package" / "Cargo.toml"
    target_cargo.parent.mkdir(parents=True)
    target_cargo.write_text(
        '[package]\nname = "leaked"\nversion = "0.1.0"\n'
    )
    comps = discover_components(tmp_path)
    assert "leaked" not in comps


def test_go_module_at_root(tmp_path: Path):
    (tmp_path / "go.mod").write_text(
        "module github.com/foo/bar\n\ngo 1.21\n"
    )
    (tmp_path / "main.go").write_text("package main\n")
    comps = discover_components(tmp_path)
    assert "bar" in comps
    assert comps["bar"].bump_files == []
    assert "go.mod" in comps["bar"].paths
    assert "**/*.go" in comps["bar"].paths


def test_go_module_strips_major_version_suffix(tmp_path: Path):
    (tmp_path / "go.mod").write_text(
        "module github.com/foo/bar/v3\n\ngo 1.21\n"
    )
    comps = discover_components(tmp_path)
    assert "bar" in comps
    assert "v3" not in comps


def test_go_module_keeps_v_when_part_of_name(tmp_path: Path):
    # 'va' is not a major version (digits required after the 'v')
    (tmp_path / "go.mod").write_text("module example.com/va\n")
    comps = discover_components(tmp_path)
    assert "va" in comps


def test_go_module_in_subdirectory(tmp_path: Path):
    sub = tmp_path / "services" / "api"
    sub.mkdir(parents=True)
    (sub / "go.mod").write_text("module example.com/api\n")
    comps = discover_components(tmp_path)
    assert "api" in comps
    assert comps["api"].paths == ["services/api/**"]


def test_go_module_in_vendor_skipped(tmp_path: Path):
    (tmp_path / "go.mod").write_text("module example.com/main\n")
    vend = tmp_path / "vendor" / "junk"
    vend.mkdir(parents=True)
    (vend / "go.mod").write_text("module leaked\n")
    comps = discover_components(tmp_path)
    assert "main" in comps
    assert "leaked" not in comps
    assert "junk" not in comps


def test_gradle_with_settings_groovy(tmp_path: Path):
    (tmp_path / "gradle.properties").write_text(
        "# build settings\nversion=1.2.3\ngroup=com.example\n"
    )
    (tmp_path / "settings.gradle").write_text(
        "rootProject.name = 'myapp'\n"
    )
    (tmp_path / "build.gradle").write_text("// noop\n")
    (tmp_path / "src").mkdir()
    comps = discover_components(tmp_path)
    assert "myapp" in comps
    assert comps["myapp"].bump_files[0].key == "version"
    assert str(comps["myapp"].bump_files[0].file) == "gradle.properties"
    assert "src/**" in comps["myapp"].paths
    assert "build.gradle" in comps["myapp"].paths
    assert "settings.gradle" in comps["myapp"].paths


def test_gradle_with_settings_kotlin(tmp_path: Path):
    (tmp_path / "gradle.properties").write_text("version=2.0.0\n")
    (tmp_path / "settings.gradle.kts").write_text(
        'rootProject.name = "kotlin-app"\n'
    )
    comps = discover_components(tmp_path)
    assert "kotlin-app" in comps


def test_gradle_without_settings_falls_back_to_dirname(tmp_path: Path):
    project = tmp_path / "myproj"
    project.mkdir()
    (project / "gradle.properties").write_text("version=1.0.0\n")
    comps = discover_components(project)
    assert "myproj" in comps


def test_gradle_without_version_in_properties_skipped(tmp_path: Path):
    (tmp_path / "gradle.properties").write_text("group=com.example\n")
    (tmp_path / "settings.gradle").write_text(
        "rootProject.name = 'noversion'\n"
    )
    comps = discover_components(tmp_path)
    assert "noversion" not in comps


def test_chart_in_venv_is_skipped(tmp_path: Path):
    _python_project(tmp_path)
    venv = tmp_path / ".venv" / "some" / "Chart.yaml"
    venv.parent.mkdir(parents=True)
    venv.write_text("apiVersion: v2\nname: leaked\nversion: 0.1.0\n")

    comps = discover_components(tmp_path)
    assert "leaked" not in comps


def test_no_components(tmp_path: Path):
    assert discover_components(tmp_path) == {}


def test_chart_uses_dir_name_when_chart_yaml_missing_name(tmp_path: Path):
    chart_dir = tmp_path / "charts" / "from-dir"
    chart_dir.mkdir(parents=True)
    (chart_dir / "Chart.yaml").write_text("apiVersion: v2\nversion: 0.1.0\n")
    comps = discover_components(tmp_path)
    assert "from-dir" in comps


def test_render_round_trips_through_config(tmp_path: Path):
    _python_project(tmp_path, name="multicz")
    _chart(tmp_path, dirname="multicz-chart")
    comps = discover_components(tmp_path)

    text = render_config(comps)
    target = tmp_path / "multicz.toml"
    target.write_text(text)

    import tomlkit
    parsed = tomlkit.parse(target.read_text()).unwrap()
    config = Config.model_validate(parsed)
    config.validate_references()
    assert set(config.components) == {"multicz", "multicz-chart"}


def test_package_json_skipped_without_name(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}\n")
    comps = discover_components(tmp_path)
    assert comps == {}


def test_package_json_creates_component(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "frontend", "version": "0.1.0"}\n')
    comps = discover_components(tmp_path)
    assert "frontend" in comps
    assert comps["frontend"].bump_files[0].key == "version"


def test_npm_workspaces_array_expands(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "monorepo", "private": true, '
        '"workspaces": ["packages/*"]}\n'
    )
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        '{"name": "web", "version": "1.0.0"}\n'
    )
    api = tmp_path / "packages" / "api"
    api.mkdir(parents=True)
    (api / "package.json").write_text(
        '{"name": "api-js", "version": "0.5.0"}\n'
    )
    comps = discover_components(tmp_path)

    assert "web" in comps
    assert "api-js" in comps
    assert "monorepo" not in comps  # root is not added when workspaces are declared
    assert comps["web"].paths == ["packages/web/**"]
    assert str(comps["web"].bump_files[0].file) == "packages/web/package.json"


def test_yarn_berry_workspaces_object(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "monorepo", "workspaces": {"packages": ["apps/*"]}}\n'
    )
    foo = tmp_path / "apps" / "foo"
    foo.mkdir(parents=True)
    (foo / "package.json").write_text('{"name": "foo", "version": "0.1.0"}\n')
    comps = discover_components(tmp_path)
    assert "foo" in comps


def test_pnpm_workspace_yaml(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "monorepo", "private": true}\n'
    )
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - 'packages/*'\n"
    )
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        '{"name": "@acme/web", "version": "1.0.0"}\n'
    )
    comps = discover_components(tmp_path)
    assert "web" in comps  # npm scope stripped
    assert "monorepo" not in comps


def test_workspace_member_without_version_skipped(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "monorepo", "workspaces": ["packages/*"]}\n'
    )
    private_pkg = tmp_path / "packages" / "private"
    private_pkg.mkdir(parents=True)
    (private_pkg / "package.json").write_text(
        '{"name": "private", "private": true}\n'  # no version
    )
    comps = discover_components(tmp_path)
    assert "private" not in comps


def test_package_json_scope_is_stripped(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"name": "@acme/widget", "version": "0.1.0"}\n'
    )
    comps = discover_components(tmp_path)
    assert "widget" in comps
