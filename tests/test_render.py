from __future__ import annotations

import importlib.util
import pathlib

import pytest

from mbse_artifact_viewer import registry, render_artifact, render_folder
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


def test_a_planned_type_says_so_rather_than_claiming_to_be_unknown(
    tmp_path, monkeypatch
):
    """Every type the spec names is built today, so this pins the rule.

    A pending type reported as "unknown" sends an engineer hunting for a
    spelling mistake that isn't there.
    """
    monkeypatch.setitem(registry.PLANNED, "hologram", "needs a holodeck")

    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: hologram, path: a.holo}\n",
    )
    assert "not implemented yet" in result.html
    assert "needs a holodeck" in result.diagnostics[0].message
    assert "unknown" not in result.diagnostics[0].message


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


def test_a_complete_html_document_gets_a_frame_of_its_own(tmp_path):
    """Its <head> is usually what makes it legible — an nbconvert export
    is 276 KB of stylesheet — so isolate it rather than discard it."""
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: html, path: page.html}\n",
        page__html=(
            "<!doctype html><html><head><style>body{color:red}</style>"
            "</head><body><p>kept</p></body></html>"
        ),
    )
    assert result.ok
    assert "<iframe" in result.html
    assert 'src="/page.html"' in result.html, "fetched, not inlined"
    assert "<p>kept</p>" not in result.html, "inside the frame, not loose"
    assert "color:red" not in result.html, "its styles cannot reach the page"


def test_a_document_is_carried_inline_when_there_is_no_serving_route(
    tmp_path,
):
    """A consumer without url_for still gets the document, via srcdoc."""

    class NoUrls:
        def __init__(self, inner):
            self._inner = inner

        def read_bytes(self, path):
            return self._inner.read_bytes(path)

        def exists(self, path):
            return self._inner.exists(path)

    (tmp_path / "page.html").write_text(
        "<!doctype html><html><body><p>kept</p></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "artifact.yaml").write_text(
        "name: x\nsections:\n  - {type: html, path: page.html}\n",
        encoding="utf-8",
    )

    result = render_artifact(NoUrls(LocalFileSource(tmp_path)), "")

    assert "srcdoc=" in result.html
    assert "&lt;p&gt;kept&lt;/p&gt;" in result.html, "escaped into the attr"


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

    @pytest.mark.parametrize(
        "name",
        [
            "Harness-001",
            "Connector-001",
            "Compliance-CDS",
            "Bracket-Assembly",
            "ANA-001",
            "Converted-CAD",
        ],
    )
    def test_the_working_examples_are_actually_clean(self, name):
        """Not one warning between them - they are what to copy."""
        if name in {"Harness-001", "Connector-001"} and not HAS_WIREVIZ:
            pytest.skip("wireviz not installed")

        result = render_folder(EXAMPLES / name, root=EXAMPLES)
        assert result.diagnostics == [], f"{name} is meant to be exemplary"

    def test_the_mechanical_example_shows_all_three_views(self):
        result = render_folder(EXAMPLES / "Bracket-Assembly", root=EXAMPLES)
        assert "keep-out" in result.html, "the drawing"
        assert 'class="mav-3d"' in result.html, "the 3D model"
        assert 'class="mav-pdf"' in result.html, "the torque schedule"
        assert "Witness marking" not in result.html, "page 2 was not asked for"


class TestBrokenExamples:
    """Broken on purpose, and named so nobody copies them."""

    def _render(self, name):
        return render_folder(EXAMPLES / "broken" / name, root=EXAMPLES)

    def test_missing_files_are_each_named_on_the_page(self):
        result = self._render("Missing-Files")
        errors = [d.message for d in result.errors]

        assert len(errors) == 4
        for missing in (
            "assembly-notes.md",
            "harness.yaml",
            "torque-spec.pdf",
            "bracket.glb",
        ):
            assert any(missing in m for m in errors)
            assert missing in result.html, "visible, not merely absent"

    def test_an_unknown_type_names_the_ones_that_exist(self):
        result = self._render("Unknown-Types")
        messages = " ".join(d.message for d in result.errors)

        assert "unknown section type 'mardown'" in messages
        assert "unknown section type 'step'" in messages
        assert "markdown" in messages, "the list is the fix for a typo"

    def test_bad_options_warn_where_they_can_and_fail_where_they_cannot(self):
        result = self._render("Bad-Options")
        warnings = [d for d in result.diagnostics if d not in result.errors]

        assert len(result.errors) == 1
        assert "not a page or page range" in result.errors[0].message
        assert len(warnings) >= 4
        assert result.html.count("mav-problem-title") == 1, (
            "one error placeholder; the four warned-about sections rendered"
        )


class TestModel3D:
    """glTF only, and page-level assets declared once."""

    def _folder(self, tmp_path, name="m.glb", options=""):
        (tmp_path / name).write_bytes(b"glTF\x02\x00\x00\x00")
        (tmp_path / "artifact.yaml").write_text(
            f"name: x\nsections:\n  - type: 3dmodel\n    path: {name}\n"
            + options,
            encoding="utf-8",
        )
        return render_folder(tmp_path)

    def test_renders_a_viewer(self, tmp_path):
        result = self._folder(tmp_path)
        assert result.ok
        assert 'class="mav-3d"' in result.html
        assert "GLTFLoader" in result.html

    def test_the_viewer_survives_being_injected_into_a_live_page(
        self, tmp_path
    ):
        """A classic script with dynamic import(), for two reasons.

        A host that injects rendered HTML into an already-loaded document
        (Model Explorer swaps reports in with htmx) cannot register an
        import map in time, so a static `import ... from "three"` never
        resolves. And a module that fails to load never runs, so it
        cannot report its own failure - dynamic import() rejects, which
        this code can catch.
        """
        result = self._folder(tmp_path)

        assert "importmap" not in result.document()
        assert 'type="module"' not in result.html
        assert 'from "three"' not in result.html
        assert "import(base" in result.html, "dynamic, so failure is catchable"
        assert ".catch(" in result.html

    def test_a_viewer_that_never_starts_says_so_in_markup(self, tmp_path):
        """The failure notice cannot be script's job.

        A module that fails to load never runs, so anything it would have
        said is never said. The fallback is markup the viewer clears on
        success.
        """
        result = self._folder(tmp_path)

        assert "mav-3d-fallback" in result.html
        assert "The 3D viewer did not start" in result.html
        assert "download" in result.html, "and the file is still reachable"
        assert "mount.replaceChildren();" in result.html, "cleared on success"

    def test_a_step_file_says_to_export_gltf(self, tmp_path):
        result = self._folder(tmp_path, name="part.step")
        assert result.errors
        assert "export glTF from your CAD" in result.html
        assert "tessellated" in result.html

    def test_z_up_is_rotated_into_gltfs_y_up_world(self, tmp_path):
        assert "rotation.x" in self._folder(
            tmp_path, options="    options:\n      up: z\n"
        ).html
        assert "rotation.x" not in self._folder(tmp_path).html

    def test_camera_is_a_direction_so_any_size_model_is_framed(self, tmp_path):
        result = self._folder(
            tmp_path, options="    options:\n      camera: [0.4, 0.3, 1.2]\n"
        )
        assert "Vector3(0.4, 0.3, 1.2)" in result.html

        bad = self._folder(tmp_path, options="    options:\n      camera: up\n")
        assert "Vector3(1.0, 1.0, 1.0)" in bad.html
        assert "not three numbers" in str(bad.diagnostics)

    def test_a_missing_model_is_reported_like_any_other_file(self, tmp_path):
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - {type: 3dmodel, path: gone.glb}\n",
            encoding="utf-8",
        )
        result = render_folder(tmp_path)
        assert "gone.glb" in result.html
        assert result.errors


def test_a_fragment_that_mentions_html_in_a_comment_is_still_a_fragment(
    tmp_path,
):
    """The naive sniff calls a fragment a document on its own explanation."""
    result = build(
        tmp_path,
        "name: x\nsections:\n  - {type: html, path: part.html}\n",
        part__html=(
            "<!-- unlike a complete <html> document, this is a fragment -->\n"
            "<p>kept</p>"
        ),
    )
    assert result.ok
    assert "<p>kept</p>" in result.html


class TestWirevizPrepend:
    """WireViz has no cross-file include; prepending text is how it shares."""

    TEMPLATE = (
        "molex_kk_254_4p: &molex_kk_254_4p\n"
        "  type: Molex KK 254\n"
        "  pinlabels: [GND, '+12V']\n"
    )
    HARNESS = (
        "connectors:\n"
        "  X1:\n"
        "    <<: *molex_kk_254_4p\n"
        "connections:\n"
        "  - - X1: [1, 2]\n"
    )

    def _build(self, tmp_path, options):
        (tmp_path / "shared").mkdir(exist_ok=True)
        (tmp_path / "shared" / "connector.yaml").write_text(
            self.TEMPLATE, encoding="utf-8"
        )
        (tmp_path / "harness.yaml").write_text(self.HARNESS, encoding="utf-8")
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - type: wireviz\n    path: harness.yaml\n"
            + options,
            encoding="utf-8",
        )
        return render_folder(tmp_path)

    @pytest.mark.skipif(not HAS_WIREVIZ, reason="wireviz not installed")
    def test_a_harness_can_borrow_a_connector_definition(self, tmp_path):
        result = self._build(
            tmp_path,
            "    options:\n      prepend: shared/connector.yaml\n",
        )
        assert result.ok
        assert "<svg" in result.html
        assert "GND" in result.html

    @pytest.mark.skipif(not HAS_WIREVIZ, reason="wireviz not installed")
    def test_without_it_the_undefined_anchor_is_reported(self, tmp_path):
        result = self._build(tmp_path, "")
        assert result.errors, "an undefined alias is not a silent empty diagram"

    def test_a_missing_prepend_names_that_file_not_the_harness(self, tmp_path):
        """The section's own path exists, so the generic message would
        point at entirely the wrong file."""
        result = self._build(
            tmp_path, "    options:\n      prepend: shared/gone.yaml\n"
        )
        assert "prepend: 'shared/gone.yaml' does not exist" in str(
            result.errors[0].message
        )


class TestCollapsingAndLinks:
    """Every artifact and section collapses to a line that stands alone."""

    def _build(self, tmp_path):
        (tmp_path / "a.md").write_text("body text", encoding="utf-8")
        (tmp_path / "artifact.yaml").write_text(
            "name: Bracket\ndescription: A mounting bracket.\n"
            "sections:\n"
            "  - {type: markdown, path: a.md, description: The notes.}\n",
            encoding="utf-8",
        )
        return render_folder(tmp_path)

    def test_the_artifact_collapses_to_its_name_and_description(
        self, tmp_path
    ):
        result = self._build(tmp_path)
        assert '<details class="mav-artifact" open>' in result.html
        assert '<summary class="mav-head">' in result.html
        assert "Bracket" in result.html
        assert "A mounting bracket." in result.html

    def test_each_section_collapses_on_its_own_and_starts_open(self, tmp_path):
        """Open by default: collapsing is a choice, not a chore to undo."""
        result = self._build(tmp_path)
        assert '<details class="mav-section" data-type="markdown" open>' in (
            result.html
        )
        assert '<span class="mav-summary-label">The notes.</span>' in result.html

    def test_a_section_without_a_description_is_labelled_by_its_file(
        self, tmp_path
    ):
        (tmp_path / "a.md").write_text("body", encoding="utf-8")
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - {type: markdown, path: a.md}\n",
            encoding="utf-8",
        )
        result = render_folder(tmp_path)
        assert '<span class="mav-summary-label">a.md</span>' in result.html

    def test_every_section_links_to_the_file_it_came_from(self, tmp_path):
        """Not only the types with a viewer - the notebook, the harness
        YAML and the Markdown are all worth opening directly."""
        result = self._build(tmp_path)
        assert 'class="mav-open" href="/a.md"' in result.html
        assert 'target="_blank"' in result.html

    def test_no_link_when_the_consumer_cannot_serve_files(self, tmp_path):
        class NoUrls:
            def __init__(self, inner):
                self._inner = inner

            def read_bytes(self, path):
                return self._inner.read_bytes(path)

            def exists(self, path):
                return self._inner.exists(path)

        (tmp_path / "a.md").write_text("body", encoding="utf-8")
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - {type: markdown, path: a.md}\n",
            encoding="utf-8",
        )
        result = render_artifact(NoUrls(LocalFileSource(tmp_path)), "")
        assert "mav-open" not in result.html
        assert "body" in result.html, "the section itself still renders"


def test_unprintable_frames_are_left_out_of_print():
    """A PDF iframe and a WebGL canvas both print blank, so a report came
    out as a page of empty boxes."""
    from mbse_artifact_viewer import EMBED_STYLESHEET

    print_rules = EMBED_STYLESHEET.split("@media print")[1]
    for selector in (".mav-pdf", ".mav-3d", ".mav-embed"):
        assert selector in print_rules
    assert "display: none" in print_rules


class TestCollapsedOption:
    """Whether sections start folded depends on why the page exists."""

    def _build(self, tmp_path, **kwargs):
        (tmp_path / "a.md").write_text("body", encoding="utf-8")
        (tmp_path / "b.md").write_text("body", encoding="utf-8")
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n"
            "  - {type: markdown, path: a.md}\n"
            "  - {type: markdown, path: b.md}\n",
            encoding="utf-8",
        )
        return render_folder(tmp_path, **kwargs)

    def _sections(self, result):
        import re

        return re.findall(r'<details class="mav-section"[^>]*>', result.html)

    def test_open_by_default(self, tmp_path):
        """The CLI shows one artifact you opened in order to look at it."""
        sections = self._sections(self._build(tmp_path))
        assert len(sections) == 2
        assert all(" open" in s for s in sections)

    def test_collapsed_folds_every_section(self, tmp_path):
        """A report embedding several artifacts is easier to scan folded."""
        sections = self._sections(self._build(tmp_path, collapsed=True))
        assert len(sections) == 2
        assert not any(" open" in s for s in sections)

    def test_the_artifact_itself_stays_open(self, tmp_path):
        """Folding it too would leave a page of nothing but names."""
        result = self._build(tmp_path, collapsed=True)
        assert '<details class="mav-artifact" open>' in result.html

    def test_the_button_says_what_it_will_do(self, tmp_path):
        assert "Collapse all</button>" in self._build(tmp_path).html
        assert (
            "Expand all</button>" in self._build(tmp_path, collapsed=True).html
        )

    def test_the_toggle_script_is_page_level_and_bound_once(self, tmp_path):
        """Delegated from `document`, so it also serves artifacts injected
        after it ran - which is how Model Explorer loads reports."""
        result = self._build(tmp_path)

        assert "mavToggleBound" in result.head
        assert "mavToggleBound" not in result.html, "not once per artifact"
        assert result.document().count("__mavToggleBound = true") == 1
