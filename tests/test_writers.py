from pathlib import Path

import pytest

from multicz.writers import WriterError, read_value, write_value


def test_toml_preserves_comments_and_keys(tmp_path: Path):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '# top comment\n'
        '[project]\n'
        'name = "x"  # inline\n'
        'version = "0.1.0"\n'
    )
    write_value(p, "project.version", "1.2.3")
    text = p.read_text()
    assert "# top comment" in text
    assert "# inline" in text
    assert read_value(p, "project.version") == "1.2.3"


def test_yaml_preserves_quotes(tmp_path: Path):
    p = tmp_path / "Chart.yaml"
    p.write_text(
        "# Helm chart\n"
        "apiVersion: v2\n"
        "name: myapp\n"
        "version: 0.1.0\n"
        'appVersion: "1.0.0"\n'
    )
    write_value(p, "appVersion", "2.0.0")
    write_value(p, "version", "0.2.0")
    text = p.read_text()
    assert "# Helm chart" in text
    assert '"2.0.0"' in text
    assert "version: 0.2.0" in text


def test_json_preserves_indent_and_order(tmp_path: Path):
    p = tmp_path / "package.json"
    p.write_text(
        '{\n'
        '    "name": "myapp",\n'
        '    "version": "0.1.0",\n'
        '    "scripts": {\n'
        '        "build": "vite build"\n'
        '    }\n'
        '}\n'
    )
    write_value(p, "version", "1.2.3")
    text = p.read_text()
    # 4-space indent preserved
    assert '    "name"' in text
    assert '    "version": "1.2.3"' in text
    # key order preserved (name before version before scripts)
    assert text.index('"name"') < text.index('"version"') < text.index('"scripts"')
    # nested mapping preserved
    assert '"build": "vite build"' in text
    assert read_value(p, "version") == "1.2.3"


def test_json_nested_key(tmp_path: Path):
    p = tmp_path / "manifest.json"
    p.write_text('{\n  "image": {\n    "tag": "1.0.0"\n  }\n}\n')
    write_value(p, "image.tag", "2.0.0")
    assert read_value(p, "image.tag") == "2.0.0"


def test_properties_round_trip(tmp_path: Path):
    p = tmp_path / "gradle.properties"
    p.write_text(
        "# build settings\n"
        "version=1.0.0\n"
        "group=com.example\n"
        "# trailing comment\n"
    )
    write_value(p, "version", "2.0.0")
    text = p.read_text()
    assert "version=2.0.0" in text
    assert "# build settings" in text
    assert "group=com.example" in text
    assert "# trailing comment" in text
    assert read_value(p, "version") == "2.0.0"


def test_properties_dotted_key_is_taken_verbatim(tmp_path: Path):
    p = tmp_path / "app.properties"
    p.write_text("release.version=1.0.0\nfoo=bar\n")
    write_value(p, "release.version", "9.9.9")
    assert "release.version=9.9.9" in p.read_text()
    assert "foo=bar" in p.read_text()


def test_properties_appends_when_key_missing(tmp_path: Path):
    p = tmp_path / "gradle.properties"
    p.write_text("group=com.example\n")
    write_value(p, "version", "1.0.0")
    text = p.read_text()
    assert "group=com.example" in text
    assert "version=1.0.0" in text


def test_plain_file_round_trip(tmp_path: Path):
    p = tmp_path / "VERSION"
    p.write_text("0.1.0\n")
    write_value(p, None, "1.2.3")
    assert p.read_text().strip() == "1.2.3"


def test_missing_key_raises(tmp_path: Path):
    p = tmp_path / "pyproject.toml"
    p.write_text("[project]\nname = \"x\"\n")
    with pytest.raises(WriterError):
        read_value(p, "project.version")


def test_missing_file_on_write_raises(tmp_path: Path):
    with pytest.raises(WriterError):
        write_value(tmp_path / "nope.toml", "x.y", "1.0.0")


def test_regex_key_python_dunder_version(tmp_path: Path):
    """The regex escape hatch lets multicz bump `__version__` in
    Python source files (and equivalently in TS/JS/Go/shell etc.)."""
    p = tmp_path / "__init__.py"
    p.write_text(
        '"""api package."""\n'
        '\n'
        '__version__ = "0.1.0"\n'
        '\n'
        'def hello() -> str:\n'
        '    return f"hi {__version__}"\n'
    )
    key = r'regex:^__version__\s*=\s*"([^"]+)"'
    assert read_value(p, key) == "0.1.0"
    write_value(p, key, "1.2.3")
    text = p.read_text()
    assert '__version__ = "1.2.3"' in text
    assert '"""api package."""' in text  # docstring untouched
    assert "def hello() -> str:" in text  # function untouched
    assert read_value(p, key) == "1.2.3"


def test_regex_key_typescript_export_const(tmp_path: Path):
    p = tmp_path / "version.ts"
    p.write_text("export const VERSION = '0.1.0';\n")
    key = r"regex:export const VERSION = '([^']+)'"
    write_value(p, key, "2.0.0")
    assert "export const VERSION = '2.0.0';" in p.read_text()


def test_regex_key_makefile(tmp_path: Path):
    p = tmp_path / "Makefile"
    p.write_text("VERSION := 0.1.0\nbuild:\n\techo $(VERSION)\n")
    key = r"regex:^VERSION\s*:=\s*(.+)$"
    write_value(p, key, "1.0.0")
    assert "VERSION := 1.0.0\n" in p.read_text()
    assert "echo $(VERSION)" in p.read_text()


def test_regex_key_no_match_raises(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text('VERSION = "0.1.0"\n')
    with pytest.raises(WriterError, match="matched nothing"):
        read_value(p, r"regex:^__version__\s*=\s*\"([^\"]+)\"")


def test_regex_key_without_capture_group_raises(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text('VERSION = "0.1.0"\n')
    with pytest.raises(WriterError, match="capture group"):
        read_value(p, r"regex:VERSION = \"[^\"]+\"")  # no group


def test_regex_key_invalid_pattern_raises(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text('x = "y"\n')
    with pytest.raises(WriterError, match="invalid regex"):
        read_value(p, r"regex:[unclosed")


def test_regex_key_only_first_match_replaced(tmp_path: Path):
    """Multiple matches: only the first capture group is rewritten,
    so a build script with `OLD = "1.0"` and `NEW = "1.0"` won't
    silently mass-rewrite."""
    p = tmp_path / "version.txt"
    p.write_text('A = "0.1.0"\nB = "0.1.0"\n')
    key = r'regex:= "([^"]+)"'
    write_value(p, key, "9.9.9")
    assert p.read_text() == 'A = "9.9.9"\nB = "0.1.0"\n'
