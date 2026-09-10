from __future__ import annotations

import pytest

from mbse_artifact_viewer.errors import PathError
from mbse_artifact_viewer.paths import join_relative, normalize_folder


def test_resolves_relative_to_the_manifest_folder():
    assert join_relative("pcbs/PCBA", "notes.md") == "pcbs/PCBA/notes.md"


def test_upward_traversal_is_allowed():
    """The motivating case from the spec: one shared datasheet."""
    assert (
        join_relative("pcbs/PCBA", "../../datasheets/molex.pdf")
        == "datasheets/molex.pdf"
    )


def test_traversal_above_the_root_is_refused():
    with pytest.raises(PathError, match="above the root"):
        join_relative("pcbs", "../../outside.md")


@pytest.mark.parametrize(
    "raw", ["/etc/passwd", "C:/models/x.md", r"C:\models\x.md", "//server/x"]
)
def test_absolute_paths_are_refused_in_either_spelling(raw):
    """The naive check is wrong on Windows, so both flavours are tested."""
    with pytest.raises(PathError, match="absolute"):
        join_relative("pcbs", raw)


@pytest.mark.parametrize("raw", ["", "   ", None, 3])
def test_unusable_paths_are_refused(raw):
    with pytest.raises(PathError):
        join_relative("pcbs", raw)


def test_backslashes_are_normalized():
    assert join_relative("a", r"sub\notes.md") == "a/sub/notes.md"


def test_current_directory_segments_are_collapsed():
    assert join_relative("a/b", "./c/./d.md") == "a/b/c/d.md"


def test_resolving_to_the_root_itself_is_refused():
    with pytest.raises(PathError, match="root itself"):
        join_relative("a", "..")


def test_normalize_folder():
    assert normalize_folder("") == ""
    assert normalize_folder("a/./b/") == "a/b"
