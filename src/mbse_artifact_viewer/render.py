"""Rendering an artifact folder to HTML.

The entry points are :func:`render_artifact` (give it a
:class:`~.sources.FileSource` and a root-relative folder - this is what
Model Explorer calls) and :func:`render_folder` (give it a directory on
disk - this is what the CLI calls).

Both return a :class:`RenderResult`: an HTML *fragment* plus the
diagnostics collected on the way. The fragment is what a consumer embeds;
:meth:`RenderResult.document` wraps it in a standalone page with the
stylesheet inlined, for the CLI.
"""

from __future__ import annotations

import dataclasses
import html
import pathlib

from . import manifest as manifest_mod
from . import registry
from .errors import ArtifactError, Diagnostic, Level, SectionError
from .renderers import markdown_
from .sources import FileSource, LocalFileSource

STYLESHEET = """
.mav { --mav-fg: #1a1d21; --mav-muted: #5c6570; --mav-line: #dfe3e8;
  --mav-bg: #ffffff; --mav-warn-bg: #fff6e5; --mav-warn-line: #e0a33a;
  color: var(--mav-fg); background: var(--mav-bg);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
@media (prefers-color-scheme: dark) {
  .mav { --mav-fg: #e6e8ea; --mav-muted: #9aa4af; --mav-line: #343a41;
    --mav-bg: #16191c; --mav-warn-bg: #3a2f18; --mav-warn-line: #c9922e; } }
.mav-head { border-bottom: 1px solid var(--mav-line); margin-bottom: 1.5rem;
  padding-bottom: .75rem; }
.mav-head h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.mav-lede { color: var(--mav-muted); margin: 0; }
.mav-section { border-top: 1px solid var(--mav-line); margin-top: 1.5rem;
  padding-top: 1.25rem; }
.mav-section:first-of-type { border-top: 0; margin-top: 0; padding-top: 0; }
.mav-caption { color: var(--mav-muted); font-size: .92rem; margin: 0 0 .6rem; }
.mav-body { overflow-x: auto; }
.mav-body svg, .mav-body img { max-width: 100%; height: auto; }
.mav-body table { border-collapse: collapse; }
.mav-body th, .mav-body td { border: 1px solid var(--mav-line);
  padding: .3rem .55rem; text-align: left; }
.mav-body pre { background: color-mix(in srgb, var(--mav-fg) 6%, transparent);
  overflow-x: auto; padding: .7rem .9rem; }
.mav-pdf { width: 100%; border: 1px solid var(--mav-line);
  background: var(--mav-bg); display: block; }
.mav-problem { background: var(--mav-warn-bg);
  border-left: 3px solid var(--mav-warn-line); padding: .8rem 1rem; }
.mav-problem p { margin: 0 0 .3rem; }
.mav-problem p:last-child { margin-bottom: 0; }
.mav-problem-title { font-weight: 600; }
.mav-problem-detail { color: var(--mav-muted); font-size: .92rem; }
.mav-problem code { font-size: .92em; }
"""


@dataclasses.dataclass
class RenderResult:
    """An artifact folder, rendered."""

    html: str
    diagnostics: list[Diagnostic]
    manifest: manifest_mod.Manifest | None = None

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level is Level.ERROR]

    @property
    def ok(self) -> bool:
        """Whether everything declared actually rendered."""
        return not self.diagnostics

    def document(self, title: str | None = None) -> str:
        """Wrap the fragment in a standalone page."""
        name = title or (self.manifest.name if self.manifest else "Artifact")
        return (
            "<!doctype html>\n"
            '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,'
            'initial-scale=1">\n'
            f"<title>{html.escape(name)}</title>\n"
            "<style>\nbody { margin: 0; padding: 2rem 1.5rem; }\n"
            f"{STYLESHEET}</style>\n</head>\n<body>\n{self.html}\n"
            "</body>\n</html>\n"
        )


def render_artifact(source: FileSource, folder: str = "") -> RenderResult:
    """Render the artifact folder at ``folder`` (root-relative).

    Never raises for content problems: a folder that cannot be read at
    all comes back as an error card, and a section that cannot be
    rendered comes back as a placeholder in its own slot. The caller
    reads :attr:`RenderResult.diagnostics` to find out.
    """
    try:
        parsed, diagnostics = manifest_mod.load(source, folder)
    except ArtifactError as err:
        diagnostic = Diagnostic(Level.ERROR, str(err), folder=folder)
        return RenderResult(_error_card(err), [diagnostic])

    parts = [
        "<article class=\"mav\">",
        _head(parsed),
    ]
    if parsed.doc:
        parts.append(
            _doc_block(source, parsed, parsed.doc, section=None)
        )
    for section in parsed.sections:
        parts.append(_render_section(source, parsed, section, diagnostics))
    parts.append("</article>")

    return RenderResult("\n".join(p for p in parts if p), diagnostics, parsed)


def render_folder(
    folder: str | pathlib.Path, root: str | pathlib.Path | None = None
) -> RenderResult:
    """Render a folder on disk.

    ``root`` is how far ``../`` in a manifest may climb. The CLI passes
    the checkout it was started in; left out, the artifact folder itself
    is the root, and any upward traversal is reported as reaching outside
    what this consumer can read.
    """
    folder = pathlib.Path(folder).resolve()
    if root is None:
        return render_artifact(LocalFileSource(folder), "")

    root = pathlib.Path(root).resolve()
    try:
        relative = folder.relative_to(root)
    except ValueError:
        raise ValueError(f"{folder} is not inside root {root}") from None
    return render_artifact(LocalFileSource(root), relative.as_posix())


def _head(parsed: manifest_mod.Manifest) -> str:
    lede = (
        f'\n<p class="mav-lede">{html.escape(parsed.description)}</p>'
        if parsed.description
        else ""
    )
    return (
        f'<header class="mav-head">\n<h1>{html.escape(parsed.name)}</h1>'
        f"{lede}\n</header>"
    )


def _render_section(
    source: FileSource,
    parsed: manifest_mod.Manifest,
    section: manifest_mod.Section,
    diagnostics: list[Diagnostic],
) -> str:
    attr = f' data-type="{html.escape(section.type)}"' if section.type else ""

    if section.error:
        diagnostics.append(_error(parsed, section, section.error))
        return _problem(section, section.error, attr)

    spec = registry.get(section.type)
    if spec is None:
        message = (
            f"section type {section.type!r} is not implemented yet - "
            f"{registry.PLANNED[section.type]}"
            if section.type in registry.PLANNED
            else (
                f"unknown section type {section.type!r} - this renderer "
                f"knows: {', '.join(registry.known_types())}"
            )
        )
        diagnostics.append(_error(parsed, section, message))
        return _problem(section, message, attr)

    ctx = registry.RenderContext(source, parsed, section, diagnostics)
    registry.check_options(ctx, spec)

    head = ""
    if section.description:
        head += (
            f'\n<p class="mav-caption">{html.escape(section.description)}</p>'
        )
    if section.doc:
        head += "\n" + _doc_block(source, parsed, section.doc, section)

    try:
        body = spec.func(ctx)
    except SectionError as err:
        diagnostics.append(_error(parsed, section, str(err)))
        return _problem(section, str(err), attr)
    except FileNotFoundError:
        message = f"declared file {section.path!r} does not exist"
        diagnostics.append(_error(parsed, section, message))
        return _problem(section, message, attr)
    except OSError as err:
        message = f"cannot read {section.path!r}: {err}"
        diagnostics.append(_error(parsed, section, message))
        return _problem(section, message, attr)

    return (
        f'<section class="mav-section"{attr}>{head}\n'
        f'<div class="mav-body">\n{body}\n</div>\n</section>'
    )


def _doc_block(
    source: FileSource,
    parsed: manifest_mod.Manifest,
    doc: str,
    section: manifest_mod.Section | None,
) -> str:
    """Render a ``doc:`` field - the long-form intro, not a section.

    A missing ``doc`` is a warning rather than an error card: the prose
    is missing, but everything it introduces is still there and still
    worth showing.
    """
    ctx = registry.RenderContext(
        source, parsed, section or manifest_mod.Section(index=-1, type="doc")
    )
    try:
        text = ctx.read_text(doc)
    except (SectionError, FileNotFoundError, OSError) as err:
        detail = str(err) or f"{doc!r} does not exist"
        return _problem_block(
            f"the doc file {doc!r} could not be read", detail
        )
    return f'<div class="mav-body mav-doc">\n{markdown_.to_html(text)}\n</div>'


def _problem(
    section: manifest_mod.Section, message: str, attr: str
) -> str:
    what = section.type or "section"
    title = f"{what} section {section.index} could not be rendered"
    detail = message
    if section.path:
        detail = f"declared path: {section.path} - {message}"
    return (
        f'<section class="mav-section mav-problem"{attr}>\n'
        f'<p class="mav-problem-title">{html.escape(title)}</p>\n'
        f'<p class="mav-problem-detail">{html.escape(detail)}</p>\n'
        "</section>"
    )


def _problem_block(title: str, detail: str) -> str:
    return (
        '<div class="mav-problem">\n'
        f'<p class="mav-problem-title">{html.escape(title)}</p>\n'
        f'<p class="mav-problem-detail">{html.escape(detail)}</p>\n'
        "</div>"
    )


def _error_card(err: ArtifactError) -> str:
    return (
        '<article class="mav">\n'
        + _problem_block("This artifact could not be read", str(err))
        + "\n</article>"
    )


def _error(
    parsed: manifest_mod.Manifest,
    section: manifest_mod.Section,
    message: str,
) -> Diagnostic:
    return Diagnostic(
        Level.ERROR,
        message,
        folder=parsed.folder,
        section=section.index,
        type=section.type or None,
    )
