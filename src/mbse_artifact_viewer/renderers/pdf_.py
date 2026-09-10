"""The ``pdf`` section type.

Unlike every Phase 1 type, a PDF cannot be inlined into the page: a
browser needs a real URL to point its viewer at, and will not open a
document handed to it as a ``data:`` URI. So this type is the first that
depends on the consumer offering a file-serving route - ``url_for`` on
its :class:`~mbse_artifact_viewer.sources.FileSource`. A consumer without
one gets a placeholder saying exactly that, rather than an empty frame.

``options: {pages: "14-15"}`` means *only those pages*. The selection is
passed along in the URL and the serving side does the extraction, so what
reaches the browser is a two-page document, not a 34-page one scrolled to
page 14.
"""

from __future__ import annotations

import html

from .. import pdfpages
from ..errors import SectionError
from ..registry import RenderContext, renderer
from ..sources import url_for

DEFAULT_HEIGHT = 720


@renderer("pdf", options={"pages", "height"})
def render(ctx: RenderContext) -> str:
    path = ctx.require_path()
    resolved = ctx.resolve(path)
    if not ctx.source.exists(resolved):
        raise FileNotFoundError(path)

    pages = _selection(ctx, resolved)
    params = {"pages": pdfpages.format_selection(pages)} if pages else None

    url = url_for(ctx.source, resolved, params)
    whole = url_for(ctx.source, resolved)
    if url is None or whole is None:
        raise SectionError(
            "this consumer has no file-serving route, so a PDF cannot be "
            "displayed - it needs a FileSource with url_for()"
        )

    # #page=1 rather than the first selected number: after extraction the
    # selection *is* the document, and its first page is page 1.
    return (
        f'<iframe class="mav-pdf" src="{html.escape(url)}#page=1" '
        f'height="{_height(ctx)}" loading="lazy" '
        f'title="{html.escape(path)}"></iframe>\n'
        f'<p class="mav-caption">{_caption(ctx, pages, whole, path)}</p>'
    )


def _selection(ctx: RenderContext, resolved: str) -> list[int]:
    """The requested pages, clamped to the ones that exist."""
    spec = ctx.option("pages")
    if spec is None:
        return []

    try:
        pages = pdfpages.parse_selection(spec)
    except ValueError as err:
        # Not a warning: silently showing all 34 pages of a specification
        # when 2 were asked for is a worse outcome than saying so.
        raise SectionError(f"option pages: {err}") from None

    try:
        total = pdfpages.page_count(ctx.source.read_bytes(resolved))
    except pdfpages.PdfUnavailable as err:
        raise SectionError(str(err)) from None
    except Exception as err:
        raise SectionError(f"this file could not be read as a PDF: {err}")

    inside = [page for page in pages if page <= total]
    if not inside:
        raise SectionError(
            f"pages {pdfpages.format_selection(pages)} are all past the end "
            f"of a {total}-page document"
        )
    if len(inside) != len(pages):
        dropped = pdfpages.format_selection(
            [page for page in pages if page > total]
        )
        ctx.warn(f"no page {dropped} in a {total}-page document; skipped")
    return inside


def _height(ctx: RenderContext) -> int:
    height = ctx.option("height", DEFAULT_HEIGHT)
    try:
        value = int(height)
    except (TypeError, ValueError):
        ctx.warn(f"option height={height!r} is not a number; using default")
        return DEFAULT_HEIGHT
    if not 100 <= value <= 4000:
        ctx.warn(f"option height={value} is out of range; using default")
        return DEFAULT_HEIGHT
    return value


def _caption(
    ctx: RenderContext, pages: list[int], whole: str, path: str
) -> str:
    link = (
        f'<a href="{html.escape(whole)}" target="_blank" '
        f'rel="noopener">{html.escape(path.rpartition("/")[2])}</a>'
    )
    if not pages:
        return f"Full document: {link}"
    return f"Showing {pdfpages.describe(pages)} of {link}"
