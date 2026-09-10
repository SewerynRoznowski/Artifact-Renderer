"""Page selection for PDFs.

``options: {pages: "14-15"}`` means *show only those pages*, not "open at
page 14" - a reader who can scroll on to the other 32 pages of a
specification hasn't been shown an extract, they have been shown the
whole document with a suggestion. So the selected pages are extracted
into a new PDF, and that is what gets served.

The extraction happens wherever the file is served from rather than in
the renderer, because a browser will not display a PDF handed to it as a
``data:`` URI - it needs a real URL to point its viewer at.
"""

from __future__ import annotations

import io
import logging
import re

_RANGE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")

#: pypdf logs a warning per malformed cross-reference entry, and real
#: engineering PDFs are full of them - the CubeSat spec in examples/ emits
#: 34 lines on every read. They say nothing the reader of a rendered page
#: can act on, so they don't belong in a dev server's output.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfUnavailable(Exception):
    """pypdf isn't installed."""


def _pypdf():
    try:
        import pypdf
    except ImportError:
        raise PdfUnavailable(
            "pypdf is not installed - install it with "
            "'pip install mbse-artifact-viewer[pdf]'"
        ) from None
    return pypdf


def parse_selection(spec: object) -> list[int]:
    """Parse ``"1-3,7"`` into ``[1, 2, 3, 7]`` (1-based, ordered, unique).

    Accepts a bare int and a list of ints too, since YAML will hand over
    ``pages: 3`` and ``pages: [1, 5]`` as those types.
    """
    if isinstance(spec, bool):  # bool is an int; "pages: yes" is nonsense
        raise ValueError(f"{spec!r} is not a page selection")
    if isinstance(spec, int):
        parts = [str(spec)]
    elif isinstance(spec, (list, tuple)):
        parts = [str(part) for part in spec]
    elif isinstance(spec, str):
        parts = spec.split(",")
    else:
        raise ValueError(f"{spec!r} is not a page selection")

    pages: list[int] = []
    for part in parts:
        match = _RANGE.match(part)
        if not match:
            raise ValueError(
                f"{part.strip()!r} is not a page or page range "
                '(try "3", "1-4", or "1-2,7")'
            )
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1:
            raise ValueError("page numbers start at 1")
        if last < first:
            raise ValueError(f"page range {first}-{last} runs backwards")
        pages.extend(range(first, last + 1))

    ordered = sorted(set(pages))
    if not ordered:
        raise ValueError("no pages selected")
    return ordered


def format_selection(pages: list[int]) -> str:
    """The inverse of :func:`parse_selection`, collapsing runs."""
    parts: list[str] = []
    for page in pages:
        if parts:
            first, _, last = parts[-1].partition("-")
            if page == int(last or first) + 1:
                parts[-1] = f"{first}-{page}"
                continue
        parts.append(str(page))
    return ",".join(parts)


def describe(pages: list[int]) -> str:
    """A human phrasing of a selection, for a caption."""
    if len(pages) == 1:
        return f"page {pages[0]}"
    return f"pages {format_selection(pages).replace('-', '–')}"


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
