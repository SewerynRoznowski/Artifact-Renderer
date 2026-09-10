"""The ``wireviz`` section type.

Two shapes of source file turn up in practice, and the difference is not
something a manifest author should have to declare:

A **complete harness** has ``connectors:``/``cables:``/``connections:``
and renders as-is.

A **bare connector template** defines just one reusable connector as a
YAML anchor, meant to be merged into the harnesses that terminate in it
(``connectors/Connector-001/connector.yaml`` is the example in the Munin
model). It is not a complete harness, and WireViz silently drops any
connector that no connection set references - so rendering one alone
produces an empty diagram rather than an error. The fix is to append the
smallest possible self-referencing ``connections:`` block, the same trick
Model Explorer's ``interfaces.py`` and the model repo's own
``tools/render_connector.py`` use.

Which of the two a file is gets detected rather than declared, since the
file itself already says: a complete harness has ``connectors:``. The
``wrap`` option exists to override that when the guess is wrong.
"""

from __future__ import annotations

import re

import yaml

from ..errors import SectionError
from ..registry import RenderContext, renderer

#: Strip the XML prolog and DOCTYPE off WireViz's SVG. They are legal at
#: the top of a standalone .svg file and meaningless inline in HTML.
_PROLOG = re.compile(
    r"^\s*(?:<\?xml[^>]*\?>\s*|<!DOCTYPE[^>]*>\s*)+", re.IGNORECASE
)


@renderer("wireviz", options={"wrap", "designator", "prepend"})
def render(ctx: RenderContext) -> str:
    text = _prepended(ctx) + ctx.read_text(ctx.require_path())

    wrap = str(ctx.option("wrap", "auto")).lower()
    if wrap not in {"auto", "always", "never"}:
        ctx.warn(f"option wrap={wrap!r} is not auto/always/never; using auto")
        wrap = "auto"

    if wrap == "always" or (wrap == "auto" and _is_bare_template(text)):
        text = _wrap_template(text, str(ctx.option("designator", "X1")))

    return _to_svg(text)


def _prepended(ctx: RenderContext) -> str:
    """Text to put in front of the harness, per ``prepend:``.

    WireViz has no cross-file ``!include``. The way a harness shares a
    connector definition is that the template's text is placed in front
    of it before parsing, so the YAML anchor is defined by the time the
    alias is read - that is what WireViz's own ``--prepend`` flag does.
    A harness that references ``*molex_kk_254_4p`` is not valid on its
    own, and this is how it becomes valid.
    """
    prepend = ctx.option("prepend")
    if not prepend:
        return ""

    paths = [prepend] if isinstance(prepend, str) else list(prepend)
    parts = []
    for path in paths:
        try:
            parts.append(ctx.read_text(str(path)))
        except FileNotFoundError:
            # Named explicitly: the section's own `path` exists, so the
            # generic "declared file does not exist" would point at the
            # wrong file entirely.
            raise SectionError(
                f"prepend: {path!r} does not exist, so the anchors this "
                "harness references are undefined"
            ) from None
    return "\n".join(parts) + "\n"


def _is_bare_template(text: str) -> bool:
    """Whether this is a connector template rather than a full harness."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        # Let WireViz produce the parse error; it words them better.
        return False
    return isinstance(data, dict) and bool(data) and "connectors" not in data


def _wrap_template(text: str, designator: str = "X1") -> str:
    """Append a self-reference so WireViz keeps the connector in the render.

    By convention the template's single top-level key is also its anchor
    name (``molex_kk_254_4p: &molex_kk_254_4p``), so the first key
    doubles as the alias to merge from.
    """
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not data:
        raise SectionError(
            "this file has no top-level mapping, so it is neither a "
            "harness nor a connector template"
        )

    template_name = next(iter(data))
    body = data[template_name]
    pinlabels = body.get("pinlabels") or [] if isinstance(body, dict) else []
    pins = list(range(1, len(pinlabels) + 1))
    if not pins:
        raise SectionError(
            f"connector template {template_name!r} declares no 'pinlabels', "
            "so there are no pins to draw"
        )

    return (
        f"{text}\n"
        "connectors:\n"
        f"  {designator}:\n"
        f"    <<: *{template_name}\n"
        "\n"
        "connections:\n"
        f"  - - {designator}: {pins}\n"
    )


def _to_svg(text: str) -> str:
    try:
        from wireviz.wireviz import parse as wireviz_parse
    except ImportError:
        raise SectionError(
            "WireViz is not installed - install it with "
            "'pip install mbse-artifact-viewer[wireviz]' (it also needs "
            "Graphviz on PATH)"
        ) from None

    try:
        svg = wireviz_parse(text, return_types="svg")
    except Exception as err:  # WireViz raises whatever its parser hit
        raise SectionError(f"WireViz could not render this file: {err}") from err

    if isinstance(svg, bytes):
        svg = svg.decode("utf-8", errors="replace")
    return _PROLOG.sub("", svg)
