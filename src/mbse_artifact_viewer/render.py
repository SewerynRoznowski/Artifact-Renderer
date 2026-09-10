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
from .paths import join_relative
from .sources import FileSource, LocalFileSource, url_for

EMBED_STYLESHEET = """
/* Structure only: sizes, borders, spacing, and the frames that content
   is shown in. No font, no text colour, no background on the article -
   an embedded fragment must look like part of the page it is embedded
   in, and the host has already decided what that looks like.

   Every colour here is derived from `currentColor`, so a border is a
   faint version of whatever the host's text colour happens to be. That
   is what makes this work in a dark theme without knowing how the host
   switches themes: Model Explorer toggles a `dark` class, this package's
   own pages use prefers-color-scheme, and neither has to be detected. */
.mav { --mav-line: color-mix(in srgb, currentColor 22%, transparent);
  --mav-muted: color-mix(in srgb, currentColor 65%, transparent);
  --mav-wash: color-mix(in srgb, currentColor 6%, transparent);
  --mav-warn-line: #c9922e;
  --mav-warn-bg: color-mix(in srgb, #c9922e 14%, transparent); }
.mav-head { border-bottom: 1px solid var(--mav-line); margin-bottom: 1.5rem;
  padding-bottom: .75rem; cursor: pointer; display: flex; flex-wrap: wrap;
  gap: .3rem .75rem; align-items: baseline; }
.mav-head h1 { margin: 0 0 .25rem; display: inline-block; }
.mav-lede { color: var(--mav-muted); display: block; }
.mav-section { border-top: 1px solid var(--mav-line); margin-top: 1.5rem;
  padding-top: 1.25rem; }
.mav-section:first-of-type { border-top: 0; margin-top: 0; padding-top: 0; }
/* The section header doubles as the collapse control, so it carries the
   label on the left and what the section came from on the right - the
   one line that has to stand on its own when the section is closed, or
   when the page is printed and the viewer inside it cannot be. */
.mav-summary { cursor: pointer; display: flex; flex-wrap: wrap;
  gap: .3rem 1rem; align-items: baseline; justify-content: space-between;
  margin-bottom: .6rem; }
.mav-summary-label { font-weight: 600; }
.mav-toggle-all { font: inherit; font-size: .82em; line-height: 1;
  padding: .3rem .55rem; margin-left: auto; cursor: pointer; color: inherit;
  background: var(--mav-wash); border: 1px solid var(--mav-line);
  border-radius: .25rem; }
.mav-summary-meta { color: var(--mav-muted); font-size: .88em;
  display: flex; gap: .6rem; align-items: baseline; }
.mav-open { white-space: nowrap; }
.mav-artifact[open] > .mav-head, .mav-section[open] > .mav-summary {
  margin-bottom: .8rem; }
.mav-caption { color: var(--mav-muted); font-size: .92em; margin: 0 0 .6rem; }
.mav-body { overflow-x: auto; }
.mav-body svg, .mav-body img { max-width: 100%; height: auto; }
.mav-body table { border-collapse: collapse; }
.mav-body th, .mav-body td { border: 1px solid var(--mav-line);
  padding: .3rem .55rem; text-align: left; }
.mav-body pre { background: var(--mav-wash); overflow-x: auto;
  padding: .7rem .9rem; }
.mav-pdf { width: 100%; border: 1px solid var(--mav-line); display: block;
  background: #fff; }
.mav-3d { width: 100%; border: 1px solid var(--mav-line); position: relative;
  background: var(--mav-wash); overflow: hidden; touch-action: none; }
.mav-3d-full { position: absolute; top: .5rem; right: .5rem; z-index: 1;
  font: inherit; font-size: .85em; line-height: 1; padding: .35rem .6rem;
  cursor: pointer; color: inherit; background: var(--mav-wash);
  border: 1px solid var(--mav-line); border-radius: .25rem; }
.mav-3d:fullscreen { height: 100% !important; border: 0; }
.mav-3d canvas { display: block; }
.mav-3d-fallback { color: var(--mav-muted); font-size: .92em; margin: 0;
  padding: 1.2rem; text-align: center; }
/* A framed document paints its own background; white is the safe ground
   for one that does not, since its text will be dark by default. */
.mav-embed { width: 100%; border: 1px solid var(--mav-line); display: block;
  background: #fff; }
.mav-nb-out { margin: .6rem 0; overflow-x: auto; }
.mav-nb-out img, .mav-nb-out svg { max-width: 100%; height: auto; }
.mav-nb-out table { border-collapse: collapse; font-size: .92em; }
.mav-nb-out th, .mav-nb-out td { border: 1px solid var(--mav-line);
  padding: .25rem .5rem; text-align: left; }
.mav-nb-source, .mav-nb-text, .mav-nb-err { font-size: .88em;
  overflow-x: auto; padding: .6rem .8rem; margin: .5rem 0;
  background: var(--mav-wash); }
.mav-nb-source { border-left: 3px solid var(--mav-line); }
.mav-nb-err { background: var(--mav-warn-bg);
  border-left: 3px solid var(--mav-warn-line); }
.mav-problem { background: var(--mav-warn-bg);
  border-left: 3px solid var(--mav-warn-line); padding: .8rem 1rem; }
.mav-problem p { margin: 0 0 .3rem; }
.mav-problem p:last-child { margin-bottom: 0; }
.mav-problem-title { font-weight: 600; }
.mav-problem-detail { color: var(--mav-muted); font-size: .92em; }
.mav-problem code { font-size: .92em; }

/* Print. An iframe holding a PDF and a WebGL canvas both come out blank
   on paper, so a printed report showed a page of empty boxes. Neither is
   printable in any useful sense, so neither is printed: what remains is
   the summary line, which names the content and links to the file it
   came from. A collapsed section stays collapsed - that was a choice -
   but nothing that was open turns into a blank rectangle. */
@media print {
  .mav-pdf, .mav-3d, .mav-embed { display: none; }
  .mav-summary, .mav-head { cursor: auto; }
  .mav-toggle-all { display: none; }
  .mav-summary-meta::after { content: " (not printable - see the link)";
    font-style: italic; }
  .mav-section:not(:has(.mav-pdf, .mav-3d, .mav-embed)) .mav-summary-meta::after
    { content: ""; }
  .mav-section, .mav-artifact { break-inside: avoid; }
  .mav-body { overflow: visible; }
}
"""

#: One delegated listener for every "Collapse all" button on the page,
#: installed once however many artifacts are on it. A classic script,
#: because rendered HTML is often injected into an already-loaded
#: document, and delegated from `document`, because it must also work for
#: artifacts injected after it ran.
TOGGLE_SCRIPT = """<script>
(function () {
  if (window.__mavToggleBound) return;
  window.__mavToggleBound = true;
  document.addEventListener("click", function (ev) {
    var button = ev.target.closest("[data-mav-toggle]");
    if (!button) return;
    /* The button lives inside a <summary>; without this, the click
       would also fold the artifact it belongs to. */
    ev.preventDefault();
    ev.stopPropagation();
    var artifact = button.closest(".mav-artifact");
    if (!artifact) return;
    var sections = artifact.querySelectorAll(".mav-section");
    var anyClosed = Array.prototype.some.call(sections, function (s) {
      return !s.open;
    });
    Array.prototype.forEach.call(sections, function (s) {
      s.open = anyClosed;
    });
    button.textContent = anyClosed ? "Collapse all" : "Expand all";
  });
})();
</script>"""

#: Typography and a palette, for a page that has none of its own - the
#: CLI's standalone output. A host application should not use this: it
#: would be overriding decisions the host has already made.
PAGE_STYLESHEET = """
.mav { color: #1a1d21; background: #ffffff;
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
.mav-head h1 { font-size: 1.5rem; }
@media (prefers-color-scheme: dark) {
  .mav { color: #e6e8ea; background: #16191c; } }
"""

#: Everything, for a standalone page. Kept under the original name
#: because that is what :meth:`RenderResult.document` needs.
STYLESHEET = PAGE_STYLESHEET + EMBED_STYLESHEET


@dataclasses.dataclass
class RenderResult:
    """An artifact folder, rendered."""

    html: str
    diagnostics: list[Diagnostic]
    manifest: manifest_mod.Manifest | None = None
    #: Markup some section types need once per page - a viewer library,
    #: an import map. A consumer embedding :attr:`html` must emit this
    #: too, above the fragment; :meth:`document` does it for you.
    head: str = ""

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
            f"{STYLESHEET}</style>\n{self.head}\n</head>\n<body>\n"
            f"{self.html}\n</body>\n</html>\n"
        )


def render_artifact(
    source: FileSource, folder: str = "", *, collapsed: bool = False
) -> RenderResult:
    """Render the artifact folder at ``folder`` (root-relative).

    ``collapsed`` starts every section folded, leaving the artifact as a
    list of labelled lines. Which is right depends on why the page
    exists: the CLI's own pages show one artifact you opened in order to
    look at it, so they start open; a report embedding several artifacts
    among other content is easier to scan folded. Either way the reader
    can change it, per section or all at once.

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
        '<article class="mav">',
        '<details class="mav-artifact" open>',
        _head(parsed, collapsed),
    ]
    head_assets: dict[str, str] = {"toggle": TOGGLE_SCRIPT}
    if parsed.doc:
        parts.append(
            _doc_block(source, parsed, parsed.doc, section=None)
        )
    for section in parsed.sections:
        parts.append(
            _render_section(
                source, parsed, section, diagnostics, head_assets, collapsed
            )
        )
    parts.append("</details>")
    parts.append("</article>")

    return RenderResult(
        "\n".join(p for p in parts if p),
        diagnostics,
        parsed,
        "\n".join(head_assets.values()),
    )


def render_folder(
    folder: str | pathlib.Path,
    root: str | pathlib.Path | None = None,
    *,
    collapsed: bool = False,
) -> RenderResult:
    """Render a folder on disk.

    ``root`` is how far ``../`` in a manifest may climb. The CLI passes
    the checkout it was started in; left out, the artifact folder itself
    is the root, and any upward traversal is reported as reaching outside
    what this consumer can read.
    """
    folder = pathlib.Path(folder).resolve()
    if root is None:
        return render_artifact(LocalFileSource(folder), "", collapsed=collapsed)

    root = pathlib.Path(root).resolve()
    try:
        relative = folder.relative_to(root)
    except ValueError:
        raise ValueError(f"{folder} is not inside root {root}") from None
    return render_artifact(
        LocalFileSource(root), relative.as_posix(), collapsed=collapsed
    )


def _head(parsed: manifest_mod.Manifest, collapsed: bool) -> str:
    """The artifact's summary: the name and description, always shown.

    It is a ``<summary>`` because the artifact is a ``<details>``:
    collapsing one leaves exactly this line, which is what a reader
    scanning a page of several artifacts wants, and what a printed page
    can show in place of an embedded viewer it cannot draw.
    """
    lede = (
        f'\n<span class="mav-lede">{html.escape(parsed.description)}</span>'
        if parsed.description
        else ""
    )
    # The button sits inside the summary, where a click would otherwise
    # toggle the artifact itself; the handler stops that.
    toggle = (
        f'\n<button type="button" class="mav-toggle-all" data-mav-toggle>'
        f'{"Expand all" if collapsed else "Collapse all"}</button>'
    )
    return (
        f'<summary class="mav-head">\n<h1>{html.escape(parsed.name)}</h1>'
        f"{lede}{toggle}\n</summary>"
    )


def _source_link(
    source: FileSource,
    parsed: manifest_mod.Manifest,
    section: manifest_mod.Section,
) -> str:
    """A link to the section's own file, for opening in a new tab.

    Every section has a ``path``, so every section can offer the thing it
    was rendered from - the PDF, the notebook, the harness YAML. On a
    page that cannot show a viewer (print, or a browser without WebGL)
    this is what remains, and an engineer who wants the source rather
    than the rendering has it either way.
    """
    if not section.path:
        return ""
    try:
        url = url_for(source, join_relative(parsed.folder, section.path))
    except Exception:
        return ""
    if url is None:
        return ""
    name = section.path.rpartition("/")[2]
    return (
        f'<a class="mav-open" href="{html.escape(url)}" target="_blank" '
        f'rel="noopener">{html.escape(name)} ↗</a>'
    )


def _render_section(
    source: FileSource,
    parsed: manifest_mod.Manifest,
    section: manifest_mod.Section,
    diagnostics: list[Diagnostic],
    head_assets: dict[str, str],
    collapsed: bool = False,
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

    ctx = registry.RenderContext(
        source, parsed, section, diagnostics, head_assets
    )
    registry.check_options(ctx, spec)

    doc = (
        "\n" + _doc_block(source, parsed, section.doc, section)
        if section.doc
        else ""
    )

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

    # Open by default: collapsing is something a reader chooses, not
    # something they have to undo before they can read the page.
    label = section.description or _default_label(section)
    return (
        f'<details class="mav-section"{attr}{"" if collapsed else " open"}>\n'
        f'<summary class="mav-summary">'
        f'<span class="mav-summary-label">{html.escape(label)}</span>'
        f'<span class="mav-summary-meta">{html.escape(section.type)}'
        f"{_source_link(source, parsed, section)}</span></summary>{doc}\n"
        f'<div class="mav-body">\n{body}\n</div>\n</details>'
    )


def _default_label(section: manifest_mod.Section) -> str:
    """What to call a section that carries no description."""
    if section.path:
        return section.path.rpartition("/")[2]
    return section.type


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
