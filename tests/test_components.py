from multicz.components import ComponentMatcher
from multicz.config import Component


def test_first_match_wins():
    matcher = ComponentMatcher({
        "api": Component(paths=["src/**", "pyproject.toml"]),
        "chart": Component(paths=["charts/**"]),
    })
    assert matcher.match("src/main.py") == "api"
    assert matcher.match("pyproject.toml") == "api"
    assert matcher.match("charts/myapp/values.yaml") == "chart"


def test_unowned_returns_none():
    matcher = ComponentMatcher({"api": Component(paths=["src/**"])})
    assert matcher.match("README.md") is None


def test_exclude_paths_take_priority():
    matcher = ComponentMatcher({
        "chart": Component(
            paths=["charts/**"],
            exclude_paths=["charts/**/values.yaml"],
        ),
    })
    assert matcher.match("charts/myapp/templates/d.yaml") == "chart"
    assert matcher.match("charts/myapp/values.yaml") is None


def test_group_buckets_files():
    matcher = ComponentMatcher({
        "api": Component(paths=["src/**"]),
        "chart": Component(paths=["charts/**"]),
    })
    grouped = matcher.group(["src/a.py", "charts/x/v.yaml", "README.md", "src/b.py"])
    assert grouped == {"api": {"src/a.py", "src/b.py"}, "chart": {"charts/x/v.yaml"}}
