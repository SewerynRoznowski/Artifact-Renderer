"""The ``html`` section type: embed a raw HTML file.

People write two different kinds of HTML file, and they need different
treatment.

A **fragment** - a bare ``<svg>``, a ``<table>``, some markup - drops
straight into the page, which is the clean case.

A **complete document** cannot. Nesting one document inside another gives
the browser something it will silently reshape, and a document's
``<head>`` is usually where the thing that makes it legible lives: an
nbconvert notebook export is 276 KB of stylesheet and 44 KB of content.
Lifting out its ``<body>`` and dropping the rest technically renders
something, and that something looks broken.

So a complete document gets its own browsing context - an ``<iframe>`` -
where its stylesheet applies to itself and cannot reach the page around
it. That is the same isolation that made dropping the ``<head>`` seem
necessary, achieved without throwing the ``<head>`` away.
"""

from __future__ import annotations

import html
import re

from ..errors import SectionError
from ..registry import RenderContext, renderer
from ..sources import url_for

_IS_DOCUMENT = re.compile(r"<(?:!doctype\s+html|html)\b", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

DEFAULT_HEIGHT = 720

#: Beyond this, srcdoc is a poor way to carry a document - it has to be
#: attribute-escaped into the page, roughly doubling it. Files this big
#: are exactly the ones a file-serving route should be handing over.
SRCDOC_LIMIT = 256 * 1024


@renderer("html", options={"height"})
def render(ctx: RenderContext) -> str:
    path = ctx.require_path()
    text = ctx.read_text(path)

    # Sniff with comments removed. A fragment whose comment explains what
    # a complete document would look like is still a fragment, and the
    # naive check calls it a document on the strength of the explanation.
    if not _IS_DOCUMENT.search(_COMMENT.sub("", text)):
        return text

    height = _height(ctx)
    url = url_for(ctx.source, ctx.resolve(path))
    if url is not None:
        frame = f'<iframe class="mav-embed" src="{html.escape(url)}"'
    elif len(text) <= SRCDOC_LIMIT:
        frame = (
            f'<iframe class="mav-embed" srcdoc="{html.escape(text, quote=True)}"'
        )
    else:
        raise SectionError(
            f"{path!r} is a complete HTML document of "
            f"{len(text) // 1024} KB, which needs a file-serving route to "
            "show - this consumer's FileSource has no url_for()"
        )

    name = path.rpartition("/")[2]
    return (
        f'{frame} height="{height}" loading="lazy" '
        f'title="{html.escape(name)}"></iframe>\n'
        f'<p class="mav-caption">A complete HTML document, shown in a frame '
        f"of its own so its styles stay inside it"
        + (
            f' · <a href="{html.escape(url)}" target="_blank" '
            f'rel="noopener">{html.escape(name)}</a>'
            if url
            else ""
        )
        + "</p>"
    )


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
