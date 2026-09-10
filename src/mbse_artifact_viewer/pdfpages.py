"""Page selection for PDFs.

``options: {pages: "14-15"}`` means *show only those pages*, not "open at
page 14" - a reader who can scroll on to the other 32 pages of a
specification hasn't been shown an extract, they have been shown the
whole document with a suggestion. So the selected pages are extracted
into a new PDF, and that is what gets served.

The extraction happens wherever the file is served from rather than in
the renderer, because a browser will not display a PDF handed to it as a
``data:`` URI - it needs a real URL to point its viewer at.

The ``"1-3,7"`` syntax itself lives in :mod:`.selection`, shared with
``jupyter``'s cell selection; it is re-exported here so a caller reading
about PDFs finds it in the obvious place.
"""

from __future__ import annotations

import io
import logging

from . import selection

#: pypdf logs a warning per malformed cross-reference entry, and real
#: engineering PDFs are full of them - the CubeSat spec in examples/ emits
#: 34 lines on every read. They say nothing the reader of a rendered page
#: can act on, so they don't belong in a dev server's output.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfUnavailable(Exception):
    """pypdf isn't installed."""


def parse_selection(spec: object) -> list[int]:
    """Parse ``"1-3,7"`` into page numbers (1-based, ordered, unique)."""
    return selection.parse(spec, "page")


def format_selection(pages: list[int]) -> str:
    """The inverse of :func:`parse_selection`, collapsing runs."""
    return selection.format(pages)


def describe(pages: list[int]) -> str:
    """A human phrasing of a page selection, for a caption."""
    return selection.describe(pages, "page")


def _pypdf():
    try:
        import pypdf
    except ImportError:
        raise PdfUnavailable(
            "pypdf is not installed - install it with "
            "'pip install mbse-artifact-viewer[pdf]'"
        ) from None
    return pypdf


def page_count(data: bytes) -> int:
    """How many pages the document has."""
    return len(_pypdf().PdfReader(io.BytesIO(data)).pages)


def extract(data: bytes, pages: list[int]) -> bytes:
    """A new PDF holding only ``pages`` (1-based), in the given order."""
    pypdf = _pypdf()
    reader = pypdf.PdfReader(io.BytesIO(data))
    writer = pypdf.PdfWriter()
    for page in pages:
        if 1 <= page <= len(reader.pages):
            writer.add_page(reader.pages[page - 1])

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
