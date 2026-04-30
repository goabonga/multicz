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
