"""The ``markdown`` section type.

Also the engine behind every ``doc:`` field, which is the same
transformation pointed at a different file - see
:mod:`mbse_artifact_viewer.render` for why those are different fields.
"""

from __future__ import annotations

import functools

from ..registry import RenderContext, renderer


@functools.lru_cache(maxsize=1)
def _parser():
    from markdown_it import MarkdownIt

    # Tables earn their place in engineering notes (pinouts, torque
    # values). Linkify is left off deliberately: it would pull in another
    # dependency to auto-detect bare URLs, which nobody has asked for.
    return MarkdownIt("commonmark", {"html": True}).enable(
        ["table", "strikethrough"]
    )


def to_html(text: str) -> str:
    """Render Markdown text to an HTML fragment."""
    return _parser().render(text)


@renderer("markdown")
def render(ctx: RenderContext) -> str:
    return to_html(ctx.read_text(ctx.require_path()))
