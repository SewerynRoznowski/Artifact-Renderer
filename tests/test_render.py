from __future__ import annotations

import importlib.util
import pathlib

import pytest

from mbse_artifact_viewer import render_artifact, render_folder
from mbse_artifact_viewer.errors import Level
from mbse_artifact_viewer.sources import LocalFileSource

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples"
HAS_WIREVIZ = importlib.util.find_spec("wireviz") is not None


def build(tmp_path, manifest, **files):
    (tmp_path / "artifact.yaml").write_text(manifest, encoding="utf-8")
    for name, text in files.items():
        path = tmp_path / name.replace("__", ".")
        path.write_text(text, encoding="utf-8")
    return render_artifact(LocalFileSource(tmp_path), "")


def test_renders_sections_in_order(tmp_path):
    result = build(
        tmp_path,
        """
        name: Ordered
        sections:
          - {type: markdown, path: one.md}
          - {type: html, path: two.html}
          - {type: markdown, path: three.md}
        """,
        one__md="first",
        two__html="<p>second</p>",
        three__md="third",
    )
    assert result.ok
    assert result.html.index("first") < result.html.index("second")
    assert result.html.index("second") < result.html.index("third")


def test_a_missing_file_is_visible_and_the_rest_still_renders(tmp_path):
    result = build(
        tmp_path,
        """
        name: Partly there
        sections:
          - {type: markdown, path: gone.md}
          - {type: markdown, path: here.md}
        """,
        here__md="still here",
    )

    assert "still here" in result.html
    assert "mav-problem" in result.html
    assert "gone.md" in result.html, "the missing file must be named on the page"
    assert [d.level for d in result.diagnostics] == [Level.ERROR]


def test_a_planned_type_says_so_rather_than_claiming_to_be_unknown(tmp_path):
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: pdf, path: a.pdf}\n",
    )
    assert "not implemented yet" in result.html
    assert "Phase 2" in result.diagnostics[0].message


def test_an_unknown_type_lists_what_is_known(tmp_path):
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: step, path: a.step}\n",
    )
    assert "unknown section type 'step'" in result.diagnostics[0].message
    assert "markdown" in result.diagnostics[0].message


def test_an_unknown_option_warns_but_the_section_still_renders(tmp_path):
    result = build(
        tmp_path,
        """
        name: x
        sections:
          - {type: markdown, path: a.md, options: {depth: 2}}
        """,
        a__md="body text",
    )
    assert "body text" in result.html
    assert result.diagnostics[0].level is Level.WARNING
    assert "'depth'" in result.diagnostics[0].message


def test_an_unreadable_manifest_is_one_error_card(tmp_path):
    result = render_artifact(LocalFileSource(tmp_path), "")
    assert result.manifest is None
    assert "could not be read" in result.html
    assert result.errors


def test_doc_layers_on_top_of_description_rather_than_replacing_it(tmp_path):
    result = build(
        tmp_path,
        """
        name: Layered
        description: The one-line label.
        doc: intro.md
        sections:
          - {type: markdown, path: a.md}
        """,
        intro__md="# The long-form intro",
        a__md="section body",
    )
    assert "The one-line label." in result.html
    assert "The long-form intro" in result.html
    assert result.html.index("The one-line label") < result.html.index(
        "The long-form intro"
    )


def test_a_missing_doc_file_does_not_cost_the_sections(tmp_path):
    result = build(
        tmp_path,
        """
        name: x
        doc: gone.md
        sections:
          - {type: markdown, path: a.md}
        """,
        a__md="section body",
    )
    assert "section body" in result.html
    assert "gone.md" in result.html


def test_html_documents_are_embedded_by_their_body(tmp_path):
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: html, path: page.html}\n",
        page__html=(
            "<!doctype html><html><head><style>body{color:red}</style>"
            "</head><body><p>kept</p></body></html>"
        ),
    )
    assert "kept" in result.html
    assert "color:red" not in result.html, "head styles must not leak out"
    assert "<html" not in result.html


def test_html_fragments_are_embedded_as_they_are(tmp_path):
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: html, path: part.html}\n",
        part__html="<p>a fragment</p>",
    )
    assert "<p>a fragment</p>" in result.html
    assert result.ok


def test_escaping_above_the_root_is_reported_not_followed(tmp_path):
    inner = tmp_path / "artifacts" / "Thing"
    inner.mkdir(parents=True)
    (tmp_path / "secret.md").write_text("not for the page", encoding="utf-8")
    (inner / "artifact.yaml").write_text(
        "name: x\nsections:\n  - {type: markdown, path: ../../secret.md}\n",
        encoding="utf-8",
    )

    result = render_folder(inner, root=tmp_path / "artifacts")

    assert "not for the page" not in result.html
    assert "above the root" in result.diagnostics[0].message


def test_upward_traversal_within_the_root_works(tmp_path):
    inner = tmp_path / "artifacts" / "Thing"
    inner.mkdir(parents=True)
    shared = tmp_path / "artifacts" / "datasheets"
    shared.mkdir()
    (shared / "part.md").write_text("shared datasheet", encoding="utf-8")
    (inner / "artifact.yaml").write_text(
        "name: x\nsections:\n"
        "  - {type: markdown, path: ../datasheets/part.md}\n",
        encoding="utf-8",
    )

    result = render_folder(inner, root=tmp_path / "artifacts")

    assert result.ok
    assert "shared datasheet" in result.html


def test_document_wraps_the_fragment_with_the_stylesheet(tmp_path):
    result = build(
        tmp_path,
        "name: Titled\nsections: []\n",
    )
    document = result.document()
    assert document.startswith("<!doctype html>")
    assert "<title>Titled</title>" in document
    assert ".mav-problem" in document
    assert result.html in document


class TestExamples:
    """The shipped examples are also the acceptance test."""

    @pytest.mark.skipif(not HAS_WIREVIZ, reason="wireviz not installed")
    def test_harness_renders_completely(self):
        result = render_folder(EXAMPLES / "Harness-001", root=EXAMPLES)
        assert result.diagnostics == []
        assert "<svg" in result.html
        assert "Mating cycles" in result.html, "the shared datasheet"

    @pytest.mark.skipif(not HAS_WIREVIZ, reason="wireviz not installed")
    def test_bare_connector_template_is_wrapped_and_draws_its_pins(self):
        result = render_folder(EXAMPLES / "Connector-001", root=EXAMPLES)
        assert result.diagnostics == []
        assert "<svg" in result.html
        assert "CAN_H" in result.html

    def test_the_broken_example_shows_every_problem_and_still_renders(self):
        result = render_folder(EXAMPLES / "Bracket-Assembly", root=EXAMPLES)
        errors = [d.message for d in result.errors]

        assert "keep-out" in result.html, "the good sections still render"
        assert len(errors) == 4
        assert any("assembly-notes.md" in m for m in errors)
        assert any("'step'" in m for m in errors)
        assert sum(1 for m in errors if "not implemented yet" in m) == 2
