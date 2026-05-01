from datetime import UTC, datetime

from multicz.commits import parse_commit
from multicz.debian import (
    DebianStanza,
    format_debian_version,
    parse_top_stanza,
    parse_top_version,
    prepend_stanza,
    render_stanza,
    upstream_version,
)

SAMPLE = """\
mypackage (1.2.3-1) unstable; urgency=medium

  * Initial release.
  * Closes: #1234

 -- John Doe <john@example.com>  Mon, 15 Jan 2024 12:34:56 +0100

mypackage (1.0.0-1) unstable; urgency=low

  * Older release.

 -- Jane Doe <jane@example.com>  Sun, 01 Jan 2024 00:00:00 +0000
"""


def test_parse_top_stanza_basic():
    stanza = parse_top_stanza(SAMPLE)
    assert isinstance(stanza, DebianStanza)
    assert stanza.package == "mypackage"
    assert stanza.version == "1.2.3-1"
    assert stanza.distribution == "unstable"
    assert "Initial release" in stanza.body
    assert "Closes: #1234" in stanza.body
    assert stanza.trailer.startswith(" -- John Doe")


def test_parse_top_version():
    assert parse_top_version(SAMPLE) == "1.2.3-1"


def test_parse_empty_returns_none():
    assert parse_top_stanza("") is None
    assert parse_top_stanza("   \n\n") is None
    assert parse_top_version("") is None


def test_parse_garbage_returns_none():
    assert parse_top_stanza("just some random text\n") is None


def test_upstream_version_strips_revision():
    assert upstream_version("1.2.3") == "1.2.3"
    assert upstream_version("1.2.3-1") == "1.2.3"
    assert upstream_version("1.2.3-2ubuntu1") == "1.2.3"


def test_upstream_version_strips_epoch():
    assert upstream_version("2:1.2.3") == "1.2.3"
    assert upstream_version("2:1.2.3-5") == "1.2.3"


def test_format_debian_version():
    assert format_debian_version("1.2.3") == "1.2.3-1"
    assert format_debian_version("1.2.3", debian_revision=3) == "1.2.3-3"
    assert format_debian_version("1.2.3", epoch=2) == "2:1.2.3-1"
    assert (
        format_debian_version("1.2.3", debian_revision=4, epoch=1) == "1:1.2.3-4"
    )


def test_render_stanza_with_commits():
    when = datetime(2024, 1, 15, 12, 34, 56, tzinfo=UTC)
    commits = [
        parse_commit("aaaaaaa", "feat: add login", ()),
        parse_commit("bbbbbbb", "fix(api): null token", ()),
    ]
    text = render_stanza(
        package="myapp",
        version="1.2.3-1",
        distribution="unstable",
        urgency="medium",
        commits=commits,
        maintainer="John Doe <john@example.com>",
        when=when,
    )

    assert text.startswith("myapp (1.2.3-1) unstable; urgency=medium\n")
    assert "  * feat: Add login" in text  # capitalized
    assert "  * fix(api): Null token" in text  # scope kept, capitalized
    assert "John Doe <john@example.com>" in text
    # Date in RFC 5322 form
    assert "Mon, 15 Jan 2024 12:34:56 +0000" in text
    # Trailer line starts with single space + --
    assert "\n -- John Doe" in text


def test_render_stanza_breaking_marker():
    when = datetime(2024, 1, 15, tzinfo=UTC)
    text = render_stanza(
        package="myapp",
        version="2.0.0-1",
        commits=[parse_commit("a", "feat!: drop py3.11 support", ())],
        maintainer="x <x@y>",
        when=when,
    )
    assert "  * feat!: Drop py3.11 support" in text


def test_render_stanza_no_commits_uses_placeholder():
    when = datetime(2024, 1, 15, tzinfo=UTC)
    text = render_stanza(
        package="myapp",
        version="1.0.0-1",
        commits=[],
        maintainer="x <x@y>",
        when=when,
    )
    assert "  * No notable changes." in text


def test_render_stanza_drops_non_conventional_commits():
    when = datetime(2024, 1, 15, tzinfo=UTC)
    commits = [
        parse_commit("a", "feat: real change", ()),
        parse_commit("b", "Some random sentence with no convention", ()),
    ]
    text = render_stanza(
        package="myapp",
        version="1.0.0-1",
        commits=commits,
        maintainer="x <x@y>",
        when=when,
    )
    assert "  * feat: Real change" in text
    assert "Some random sentence" not in text


def test_render_stanza_default_distribution_is_unreleased():
    text = render_stanza(
        package="myapp",
        version="1.0.0-1",
        commits=[],
        maintainer="x <x@y>",
        when=datetime(2024, 1, 15, tzinfo=UTC),
    )
    assert "UNRELEASED;" in text


def test_prepend_stanza_to_empty():
    new = render_stanza(
        package="myapp",
        version="1.0.0-1",
        commits=[parse_commit("a", "feat: x", ())],
        maintainer="x <x@y>",
        when=datetime(2024, 1, 15, tzinfo=UTC),
    )
    out = prepend_stanza("", new)
    assert out.startswith("myapp (1.0.0-1)")


def test_prepend_stanza_separates_with_blank_line():
    existing = SAMPLE
    new = render_stanza(
        package="mypackage",
        version="2.0.0-1",
        commits=[parse_commit("a", "feat: rewrite", ())],
        maintainer="x <x@y>",
        when=datetime(2024, 2, 1, tzinfo=UTC),
    )
    out = prepend_stanza(existing, new)

    # newest stanza first
    assert out.index("2.0.0-1") < out.index("1.2.3-1")
    assert out.index("1.2.3-1") < out.index("1.0.0-1")
    # blank line between stanzas
    sep = out.split("2.0.0-1")[1].split("mypackage (1.2.3-1)")[0]
    assert "\n\n" in sep
