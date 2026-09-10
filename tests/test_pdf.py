from __future__ import annotations

import importlib.util

import pytest

from mbse_artifact_viewer import pdfpages, render_artifact, render_folder
from mbse_artifact_viewer.sources import LocalFileSource

HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
needs_pypdf = pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")


@pytest.fixture
def pdf_bytes():
    """A five-page PDF, each page a different size so they're telling."""
    pypdf = pytest.importorskip("pypdf")
    import io

    writer = pypdf.PdfWriter()
    for index in range(5):
        writer.add_blank_page(width=200 + index, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def artifact(tmp_path, pdf_bytes):
    """A folder whose manifest is written per-test."""
    (tmp_path / "doc.pdf").write_bytes(pdf_bytes)

    def build(options=""):
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - type: pdf\n    path: doc.pdf\n"
            + options,
            encoding="utf-8",
        )
        return render_folder(tmp_path)

    return build


class TestSelection:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("3", [3]),
            (3, [3]),
            ("1-4", [1, 2, 3, 4]),
            ("1-2,7", [1, 2, 7]),
            ("7,1-2", [1, 2, 7]),
            ("2,2,2", [2]),
            ([1, 5], [1, 5]),
            (" 1 - 3 ", [1, 2, 3]),
        ],
    )
    def test_parses(self, spec, expected):
        assert pdfpages.parse_selection(spec) == expected

    @pytest.mark.parametrize(
        "spec", ["one", "0", "-2", "4-1", "", "1..3", True, None, {}]
    )
    def test_refuses_nonsense(self, spec):
        with pytest.raises(ValueError):
            pdfpages.parse_selection(spec)

    @pytest.mark.parametrize(
        ("pages", "text"),
        [([3], "3"), ([1, 2, 3], "1-3"), ([1, 2, 7], "1-2,7"), ([1, 3], "1,3")],
    )
    def test_formats_back(self, pages, text):
        assert pdfpages.format_selection(pages) == text
        assert pdfpages.parse_selection(text) == pages

    def test_describes_for_a_caption(self):
        assert pdfpages.describe([3]) == "page 3"
        assert pdfpages.describe([14, 15]) == "pages 14–15"


@needs_pypdf
class TestExtract:
    def test_takes_only_the_requested_pages(self, pdf_bytes):
        assert pdfpages.page_count(pdf_bytes) == 5

        trimmed = pdfpages.extract(pdf_bytes, [2, 3])

        assert pdfpages.page_count(trimmed) == 2
        assert len(trimmed) < len(pdf_bytes)

    def test_pages_past_the_end_are_skipped(self, pdf_bytes):
        assert pdfpages.page_count(pdfpages.extract(pdf_bytes, [4, 99])) == 1


@needs_pypdf
class TestRenderer:
    def test_a_whole_document_needs_no_page_parameter(self, artifact):
        result = artifact()
        assert result.ok
        assert 'src="/doc.pdf#page=1"' in result.html
        assert "Full document" in result.html

    def test_a_selection_is_passed_to_the_serving_side(self, artifact):
        result = artifact("    options:\n      pages: '2-3'\n")
        assert result.ok
        assert 'src="/doc.pdf?pages=2-3#page=1"' in result.html
        # After extraction the selection *is* the document, so the
        # fragment is page 1 and not page 2.
        assert "Showing pages 2–3" in result.html

    def test_pages_past_the_end_warn_and_the_rest_still_shows(self, artifact):
        result = artifact("    options:\n      pages: '4-9'\n")
        assert "pages=4-5" in result.html
        assert "no page 6-9 in a 5-page document" in str(result.diagnostics)

    def test_a_selection_entirely_past_the_end_is_an_error(self, artifact):
        result = artifact("    options:\n      pages: '90-95'\n")
        assert "past the end" in result.html
        assert result.errors

    def test_an_unparseable_selection_is_an_error_not_a_silent_full_doc(
        self, artifact
    ):
        """Showing all 34 pages when 2 were asked for is the worse outcome."""
        result = artifact("    options:\n      pages: 'two to five'\n")
        assert result.errors
        assert "<iframe" not in result.html

    def test_height_is_honoured_and_nonsense_falls_back(self, artifact):
        assert 'height="900"' in artifact(
            "    options:\n      height: 900\n"
        ).html

        result = artifact("    options:\n      height: tall\n")
        assert 'height="720"' in result.html
        assert "not a number" in str(result.diagnostics)

    def test_a_missing_file_is_reported_like_any_other(self, tmp_path):
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - {type: pdf, path: gone.pdf}\n",
            encoding="utf-8",
        )
        result = render_folder(tmp_path)
        assert "gone.pdf" in result.html
        assert result.errors


class TestWithoutAFileServingRoute:
    """A consumer whose FileSource offers no url_for()."""

    def test_says_so_rather_than_showing_an_empty_frame(
        self, tmp_path, pdf_bytes
    ):
        (tmp_path / "doc.pdf").write_bytes(pdf_bytes)
        (tmp_path / "artifact.yaml").write_text(
            "name: x\nsections:\n  - {type: pdf, path: doc.pdf}\n",
            encoding="utf-8",
        )

        class NoUrls:
            def __init__(self, inner):
                self._inner = inner

            def read_bytes(self, path):
                return self._inner.read_bytes(path)

            def exists(self, path):
                return self._inner.exists(path)

        result = render_artifact(NoUrls(LocalFileSource(tmp_path)), "")

        assert "no file-serving route" in result.html
        assert "<iframe" not in result.html
