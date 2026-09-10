"""The type -> renderer registry.

A fixed, extensible vocabulary: each section type maps to exactly one
render function, and a new type is added by adding one registry entry -
never by touching a page template. That is the whole reason sections
carry a ``type`` instead of the page knowing what a harness looks like.

Types the spec has named but not yet implemented are listed in
:data:`PLANNED`, so a manifest written ahead of the renderer gets an
honest "not implemented yet" placeholder instead of being told its type
doesn't exist.
"""

from __future__ import annotations

import dataclasses
import typing as t

from .errors import Diagnostic, Level, SectionError
from .manifest import Manifest, Section
from .paths import join_relative
from .sources import FileSource, read_text


@dataclasses.dataclass
class RenderContext:
    """Everything a renderer is allowed to know.

    Note what isn't here: no model, no uuid, no PVMT property, no local
    filesystem path. A renderer sees a file source, a manifest, and one
    section - which is exactly the package's world.
    """

    source: FileSource
    manifest: Manifest
    section: Section
    diagnostics: list[Diagnostic] = dataclasses.field(default_factory=list)

    @property
    def folder(self) -> str:
        return self.manifest.folder

    def resolve(self, raw: str) -> str:
        """Resolve a manifest-declared path to a root-relative path."""
        return join_relative(self.folder, raw)

    def read_text(self, raw: str) -> str:
        """Resolve and read a manifest-declared path as text."""
        return read_text(self.source, self.resolve(raw))

    def read_bytes(self, raw: str) -> bytes:
        """Resolve and read a manifest-declared path as bytes."""
        return self.source.read_bytes(self.resolve(raw))

    def require_path(self) -> str:
        if not self.section.path:
            raise SectionError(f"a {self.section.type!r} section needs a 'path'")
        return self.section.path

    def option(self, name: str, default: t.Any = None) -> t.Any:
        return self.section.options.get(name, default)

    def warn(self, message: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                Level.WARNING,
                message,
                folder=self.folder,
                section=self.section.index,
                type=self.section.type,
            )
        )


#: A section renderer: takes a context, returns the section's HTML body.
RenderFunc = t.Callable[[RenderContext], str]


@dataclasses.dataclass(frozen=True)
class Renderer:
    name: str
    func: RenderFunc
    #: Option keys this renderer understands. Anything else in
    #: ``options:`` is a warning, never an error - a manifest written
    #: against a newer renderer stays usable on an older one.
    options: frozenset[str] = frozenset()


REGISTRY: dict[str, Renderer] = {}

#: Named in the spec, not implemented yet. Phase 2, once there is a
#: file-serving route to hang them on.
PLANNED: dict[str, str] = {
    "3dmodel": "needs the Phase 2 file-serving route",
    "jupyter": "needs Phase 2 nbformat parsing",
}


def renderer(
    name: str, *, options: t.Iterable[str] = ()
) -> t.Callable[[RenderFunc], RenderFunc]:
    """Register ``name`` as a section type. One entry, one type."""

    def decorate(func: RenderFunc) -> RenderFunc:
        REGISTRY[name] = Renderer(name, func, frozenset(options))
        return func

    return decorate


def get(name: str) -> Renderer | None:
    return REGISTRY.get(name)


def known_types() -> list[str]:
    return sorted(REGISTRY)


def check_options(ctx: RenderContext, spec: Renderer) -> None:
    """Warn about option keys this renderer doesn't understand."""
    for key in sorted(set(ctx.section.options) - spec.options):
        ctx.warn(
            f"{spec.name!r} does not understand option {key!r}, ignored"
            + (
                f" (it understands: {', '.join(sorted(spec.options))})"
                if spec.options
                else " (it takes no options)"
            )
        )


__all__ = [
    "PLANNED",
    "REGISTRY",
    "Manifest",
    "RenderContext",
    "RenderFunc",
    "Renderer",
    "Section",
    "check_options",
    "get",
    "known_types",
    "renderer",
]
