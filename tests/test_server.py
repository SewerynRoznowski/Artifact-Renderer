from __future__ import annotations

import socket
import types

import pytest

from mbse_artifact_viewer import server
from mbse_artifact_viewer.server import fingerprint, page_url


@pytest.fixture
def occupied():
    """A port that is already taken, and the port number."""
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    try:
        yield held.getsockname()[1]
    finally:
        held.close()


def test_an_unasked_for_port_moves_along_when_the_default_is_unusable(
    occupied, monkeypatch
):
    """Windows reserves whole port ranges; refusing to start is no help."""
    monkeypatch.setattr(server, "DEFAULT_PORT", occupied)

    httpd, bound = server._bind("127.0.0.1", None, server._Handler)
    with httpd:
        assert bound == occupied + 1


def test_an_explicitly_requested_port_is_never_silently_swapped(occupied):
    """A URL you already have open would otherwise be quietly wrong."""
    with pytest.raises(SystemExit) as caught:
        server._bind("127.0.0.1", occupied, server._Handler)

    assert f"port {occupied} unavailable" in str(caught.value)
    assert "-p 8931" in str(caught.value), "the message must offer a way out"


def test_the_page_is_served_at_the_folders_place_under_the_root(tmp_path):
    """So a relative link inside a Markdown file reaches the same file
    the same path would reach from the manifest."""
    folder = tmp_path / "pcbs" / "PCBA"
    folder.mkdir(parents=True)
    assert page_url(folder, tmp_path) == "/pcbs/PCBA/"


def test_a_folder_that_is_its_own_root_is_served_at_the_top(tmp_path):
    assert page_url(tmp_path, tmp_path) == "/"


def make_artifact(folder, name="x"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "artifact.yaml").write_text(
        f"name: {name}\nsections: []\n", encoding="utf-8"
    )
    return folder


def at(root, url_path):
    """Call the URL -> artifact-folder mapping with just a root."""
    return server._Handler._artifact_at(
        types.SimpleNamespace(root=root), url_path
    )


def test_every_artifact_folder_under_the_root_is_a_page(tmp_path):
    """Not only the folder the server was started with."""
    make_artifact(tmp_path / "a" / "Harness-001")
    make_artifact(tmp_path / "b" / "Connector-001")

    assert at(tmp_path, "/a/Harness-001/") == tmp_path / "a" / "Harness-001"
    assert at(tmp_path, "/b/Connector-001") == tmp_path / "b" / "Connector-001"


def test_a_folder_without_a_manifest_is_not_a_page(tmp_path):
    (tmp_path / "datasheets").mkdir()
    assert at(tmp_path, "/datasheets/") is None
    assert at(tmp_path, "/nope/") is None


def test_the_root_of_a_repository_lists_rather_than_404s(tmp_path):
    """`mav serve` with no folder is the most natural way to run it."""
    make_artifact(tmp_path / "a" / "Harness-001", name="Harness-001")

    # The root itself has no manifest, so it is a listing, not a page.
    assert at(tmp_path, "/") is None
    assert server.find_artifacts(tmp_path) == [tmp_path / "a" / "Harness-001"]


def test_an_intermediate_directory_lists_what_is_under_it(tmp_path):
    make_artifact(tmp_path / "a" / "Harness-001")
    make_artifact(tmp_path / "b" / "Connector-001")

    assert server.find_artifacts(tmp_path / "a") == [
        tmp_path / "a" / "Harness-001"
    ]


def test_dot_segments_cannot_walk_out_of_the_root(tmp_path):
    make_artifact(tmp_path / "inside")
    assert at(tmp_path, "/../../inside/") == tmp_path / "inside"


def test_find_artifacts_lists_them_and_skips_the_noise(tmp_path):
    make_artifact(tmp_path / "Harness-001")
    make_artifact(tmp_path / "nested" / "Connector-001")
    make_artifact(tmp_path / ".git" / "Ignored")
    make_artifact(tmp_path / "node_modules" / "Ignored")

    found = server.find_artifacts(tmp_path)

    assert found == [
        tmp_path / "Harness-001",
        tmp_path / "nested" / "Connector-001",
    ]


def test_opening_a_browser_reports_whether_it_worked(monkeypatch):
    monkeypatch.setattr(server.webbrowser, "open", lambda url: True)
    assert server.open_in_browser("http://127.0.0.1:8000/") is True

    monkeypatch.setattr(server.webbrowser, "open", lambda url: False)
    assert server.open_in_browser("http://127.0.0.1:8000/") is False


def test_a_machine_with_no_browser_is_not_an_error(monkeypatch):
    """Headless boxes and SSH sessions are normal places to run this."""

    def explode(url):
        raise OSError("no browser here")

    monkeypatch.setattr(server.webbrowser, "open", explode)
    assert server.open_in_browser("http://127.0.0.1:8000/") is False


def test_fingerprint_changes_when_content_changes(tmp_path):
    (tmp_path / "harness.yaml").write_text("connectors: {}", encoding="utf-8")
    before = fingerprint(tmp_path)

    (tmp_path / "harness.yaml").write_text(
        "connectors: {X1: {}}", encoding="utf-8"
    )
    assert fingerprint(tmp_path) != before


def test_fingerprint_changes_when_a_file_appears(tmp_path):
    before = fingerprint(tmp_path)
    (tmp_path / "notes.md").write_text("new", encoding="utf-8")
    assert fingerprint(tmp_path) != before
