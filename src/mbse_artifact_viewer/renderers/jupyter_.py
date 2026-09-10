"""The ``jupyter`` section type: a notebook's *results*, not its code.

An analysis notebook is a working document - imports, scratch variables,
a plot, a cell that prints a dataframe to check it. What a reviewer needs
from it is the prose and the outputs: the diagram, the table, the number
that came out. So source is hidden by default and ``include_source: true``
brings it back, which is the opposite of what a notebook viewer usually
does, and deliberately so.

Outputs are embedded as they were saved. A notebook carries its images
base64-encoded inside the ``.ipynb``, so a plot needs no second file and
no file-serving route - unlike ``pdf`` and ``3dmodel``, this type works
against any :class:`~mbse_artifact_viewer.sources.FileSource`.

Parsed with :mod:`json` rather than ``nbformat``. The format is a
documented JSON schema and this reads four keys of it; a dependency that
exists to validate notebooks earns its place in a tool that *writes*
them, not one that shows them.
"""

from __future__ import annotations

import base64
import html
import json
import re

from .. import selection as selection_mod
from ..errors import SectionError
from ..registry import RenderContext, renderer
from . import markdown_

#: Preference order for a rich output. SVG before PNG (it scales, and a
#: context diagram is vector to begin with), HTML before plain text (a
#: dataframe renders as a table), plain text last as the fallback that
#: always exists.
PREFERRED = (
    "image/svg+xml",
    "text/html",
    "image/png",
    "image/jpeg",
    "text/plain",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@renderer("jupyter", options={"cells", "tags", "include_source"})
def render(ctx: RenderContext) -> str:
    notebook = _load(ctx)
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise SectionError("this notebook has no 'cells' list")

    chosen = _choose(ctx, cells)
    include_source = bool(ctx.option("include_source", False))

    blocks = [_cell(cell, include_source) for cell in chosen]
    blocks = [block for block in blocks if block]
    if not blocks:
        ctx.warn(
            "nothing to show - the selected cells have no output. Try "
            "'include_source: true', or run the notebook before saving it"
        )
    return '<div class="mav-nb">\n' + "\n".join(blocks) + "\n</div>"


def _load(ctx: RenderContext) -> dict:
    try:
        notebook = json.loads(ctx.read_text(ctx.require_path()))
    except json.JSONDecodeError as err:
        raise SectionError(f"this file is not valid notebook JSON: {err}")
    if not isinstance(notebook, dict):
        raise SectionError("a notebook must be a JSON object")
    if notebook.get("nbformat", 4) < 4:
        raise SectionError(
            f"nbformat {notebook.get('nbformat')} is too old to read; "
            "resave the notebook from a current Jupyter"
        )
    return notebook


def _choose(ctx: RenderContext, cells: list) -> list:
    """Apply ``cells:`` and ``tags:``, in that order."""
    chosen = list(enumerate(cells, start=1))

    spec = ctx.option("cells")
    if spec is not None:
        try:
            wanted = selection_mod.parse(spec, "cell")
        except ValueError as err:
            raise SectionError(f"option cells: {err}") from None
        beyond = [n for n in wanted if n > len(cells)]
        if beyond:
            ctx.warn(
                f"no cell {selection_mod.format(beyond)} in a "
                f"{len(cells)}-cell notebook; skipped"
            )
        chosen = [(n, cell) for n, cell in chosen if n in set(wanted)]
        if not chosen:
            raise SectionError(
                f"cells {selection_mod.format(wanted)} are all past the end "
                f"of a {len(cells)}-cell notebook"
            )

    tags = ctx.option("tags")
    if tags is not None:
        wanted_tags = {tags} if isinstance(tags, str) else set(tags)
        chosen = [
            (n, cell)
            for n, cell in chosen
            if wanted_tags & set(cell.get("metadata", {}).get("tags") or ())
        ]
        if not chosen:
            ctx.warn(
                f"no cell is tagged {', '.join(sorted(wanted_tags))} - "
                "nothing to show"
            )

    return [cell for _, cell in chosen]


def _cell(cell: dict, include_source: bool) -> str:
    source = "".join(cell.get("source") or ())

    if cell.get("cell_type") == "markdown":
        return markdown_.to_html(source)

    parts = []
    if include_source and source.strip():
        parts.append(
            f'<pre class="mav-nb-source"><code>{html.escape(source)}'
            "</code></pre>"
        )
    parts += [_output(output) for output in cell.get("outputs") or ()]
    return "\n".join(part for part in parts if part)


def _output(output: dict) -> str:
    kind = output.get("output_type")

    if kind == "stream":
        text = "".join(output.get("text") or ())
        return _text(text, error=output.get("name") == "stderr")

    if kind == "error":
        traceback = "\n".join(output.get("traceback") or ())
        return _text(_ANSI.sub("", traceback) or output.get("evalue", ""), True)

    if kind in ("display_data", "execute_result"):
        data = output.get("data") or {}
        for mime in PREFERRED:
            if mime in data:
                return _rich(mime, data[mime])
        return ""

    return ""


def _rich(mime: str, payload) -> str:
    if isinstance(payload, list):
        payload = "".join(payload)

    if mime == "image/svg+xml":
        return f'<div class="mav-nb-out">{payload}</div>'
    if mime.startswith("image/"):
        # Already base64 in the notebook; keep it that way rather than
        # decoding and re-encoding it.
        encoded = payload if isinstance(payload, str) else base64.b64encode(
            payload
        ).decode()
        return (
            f'<div class="mav-nb-out"><img alt="" '
            f'src="data:{mime};base64,{encoded.strip()}"></div>'
        )
    if mime == "text/html":
        return f'<div class="mav-nb-out">{payload}</div>'
    return _text(payload)


def _text(text: str, error: bool = False) -> str:
    if not text.strip():
        return ""
    kind = "mav-nb-err" if error else "mav-nb-text"
    return f'<pre class="{kind}">{html.escape(text.rstrip())}</pre>'
