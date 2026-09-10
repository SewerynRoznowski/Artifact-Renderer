"""The ``html`` section type: embed a raw HTML file.

The one wrinkle is that people write both kinds of HTML file. A fragment
drops straight into the page. A complete document with its own
``<html>``/``<head>`` cannot - nesting one document inside another gives
the browser something it will silently reshape, and any ``<style>`` in
its head would leak out over the rest of the page. So a complete document
has its ``<body>`` lifted out, which is the part the author meant.
"""

from __future__ import annotations

import re

from ..registry import RenderContext, renderer

_BODY = re.compile(
    r"<body\b[^>]*>(?P<body>.*?)</body\s*>", re.IGNORECASE | re.DOTALL
)
_IS_DOCUMENT = re.compile(r"<(?:!doctype\s+html|html)\b", re.IGNORECASE)


@renderer("html")
def render(ctx: RenderContext) -> str:
    text = ctx.read_text(ctx.require_path())

    if not _IS_DOCUMENT.search(text):
        return text

    match = _BODY.search(text)
    if match is None:
        ctx.warn(
            "this looks like a complete HTML document but has no <body>; "
            "embedding it as-is"
        )
        return text

    ctx.warn(
        "embedded the <body> of a complete HTML document; anything in its "
        "<head> (styles, scripts) was dropped"
    )
    return match.group("body")
